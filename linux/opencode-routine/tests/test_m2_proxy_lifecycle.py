"""Offline launcher contracts; fake adapters are not network qualification."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

import test_m2 as fixtures
from test_m1 import ENTRY, LIBRARY
from routine.compose import DockerCompose, bundle_identity, worker_assets
from routine.contracts import RoutineError, canonical, digest, validate_profile
from routine.process import host_environment
from routine.proxy import ProxyCheck, proxy_document, proxy_healthcheck, proxy_policy, retained_file
from routine.sandbox import Sandbox
from routine.launcher import Launcher
from routine.store import Store


LIMITS = {"max_connections": 4, "request_seconds": 5, "idle_seconds": 10,
          "tunnel_seconds": 30, "max_tunnel_bytes": 1048576}


class FakeProxy:
    def __init__(self, mode="pass"):
        self.mode = mode
        self.calls = []

    def preflight_proxy(self, profile, bundle_sha256, artifact_id, timeout):
        self.calls.append("preflight")
        if self.mode == "preflight-fail":
            raise RoutineError("invalid_runtime", "Unapproved image")

    def start_proxy(self, directory, artifact_id, timeout):
        self.calls.append("start")
        self.document = json.loads((directory / "compose.json").read_bytes())
        if self.mode == "start-fail":
            raise RoutineError("adapter_failed", "Ambiguous creation")

    def wait_proxy_ready(self, artifact_id, profile, policy_sha256, timeout):
        self.calls.append("ready")
        if self.mode in ("timeout", "readiness-fail"):
            raise RoutineError("command_timeout" if self.mode == "timeout" else "invalid_runtime", "Not ready")

    def stop_proxy(self, directory, artifact_id, timeout):
        self.calls.append("stop")
        if self.mode == "stop-fail":
            raise RoutineError("adapter_failed", "Stop unconfirmed")


def inspection(profile, artifact_id, policy_sha256, status="healthy"):
    limits = profile["resources"]
    return {"Name": "/routine-proxy-" + artifact_id[:32], "Image": profile["runtime"]["image"],
            "Config": {"User": "10001:10001", "Labels": {"routine.artifact-id": artifact_id,
                       "routine.proxy-policy-sha256": policy_sha256, "routine.proxy-mode": "offline-check"},
                       "Entrypoint": ["python3", "-I", "-B", "/opt/routine/bundle/proxy.py", "/policy/proxy.json"],
                       "Healthcheck": {"Test": proxy_healthcheck(policy_sha256, bundle_identity())}},
            "HostConfig": {"NetworkMode": "none", "ReadonlyRootfs": True, "Privileged": False,
                           "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"],
                           "Memory": limits["memory_mb"] * 1048576, "MemorySwap": limits["memory_mb"] * 1048576,
                           "NanoCpus": int(limits["cpus"] * 10**9), "PidsLimit": limits["pids"],
                           "RestartPolicy": {"Name": "no"}, "LogConfig": {"Type": "local", "Config": {
                               "max-size": f"{limits['log_mb']}m", "max-file": "1", "compress": "false"}}},
            "Mounts": [{"Type": "bind", "Destination": "/policy/proxy.json", "RW": False}],
            "State": {"Running": True, "Health": {"Status": status}}}


class ProxyLifecycleTests(unittest.TestCase):
    write = fixtures.M2Tests.write
    fixture = fixtures.M2Tests.fixture
    save_manifest = fixtures.M2Tests.save_manifest
    authorize = fixtures.M2Tests.authorize
    expect_error = fixtures.M2Tests.expect_error
    prepare_profile = fixtures.M2Tests.prepare_profile
    git = staticmethod(fixtures.M2Tests.git)
    writable_fixture = fixtures.M2Tests.writable_fixture

    def setUp(self):
        fixtures.M2Tests.setUp(self)
        self.profile["network"] = {"allowed_domains": ["example.com"], "proxy": deepcopy(LIMITS)}
        self.prepare_profile()

    def check(self, adapter=None, clock=None, run_id="run-1"):
        authorization = self.authorize()
        adapter = adapter or FakeProxy()
        options = {} if clock is None else {"clock": clock}
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", run_id, authorization)
            result = ProxyCheck(adapter, **options).launch(session, run_id)
        return result, adapter

    def test_policy_requires_explicit_approved_limits_without_defaults(self):
        validate_profile(self.profile)
        self.assertEqual(proxy_policy(self.profile), {"allowed_domains": ["example.com"], **LIMITS})
        old = deepcopy(self.profile)
        del old["network"]["proxy"]
        validate_profile(old)
        self.expect_error("proxy_policy_missing", lambda: proxy_policy(old))
        for key in LIMITS:
            for value in (True, 0, -1, 1.5, "1"):
                profile = deepcopy(self.profile)
                profile["network"]["proxy"][key] = value
                self.expect_error("invalid_profile", lambda: validate_profile(profile))
        for key, value in (("max_connections", 65), ("request_seconds", 61), ("tunnel_seconds", 3601)):
            profile = deepcopy(self.profile)
            profile["network"]["proxy"][key] = value
            self.expect_error("invalid_profile", lambda: validate_profile(profile))
        profile = deepcopy(self.profile)
        profile["version"] = 1
        del profile["runtime"]
        self.expect_error("invalid_input", lambda: validate_profile(profile))

    def test_generated_policy_is_accepted_by_the_shipped_proxy(self):
        import test_m2_proxy
        proxy = test_m2_proxy.proxy.Proxy(**proxy_policy(self.profile))
        self.assertEqual(proxy.allowed_domains, frozenset({"example.com"}))
        self.assertEqual(proxy.max_connections, LIMITS["max_connections"])

    def test_compose_has_only_an_offline_read_only_pinned_proxy(self):
        document = proxy_document(self.profile, self.base / "policy.json", "a" * 64,
                                  digest(canonical(proxy_policy(self.profile))))
        self.assertEqual(set(document["services"]), {"proxy"})
        service = document["services"]["proxy"]
        self.assertEqual(service["network_mode"], "none")
        self.assertTrue(service["read_only"])
        self.assertEqual(service["image"], self.profile["runtime"]["image"])
        self.assertEqual(service["cap_drop"], ["ALL"])
        self.assertEqual(service["user"], "10001:10001")
        self.assertEqual(service["volumes"][0]["target"], "/policy/proxy.json")
        self.assertTrue(service["volumes"][0]["read_only"])
        for key in ("ports", "networks", "build", "devices", "environment", "tmpfs"):
            self.assertNotIn(key, service)
        path = self.base / "compose.json"
        path.write_bytes(canonical(document))
        result = subprocess.run(["/usr/bin/docker", "compose", "--env-file", "/dev/null", "--file", str(path),
                                 "config", "--format", "json"], env=host_environment(), capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_check_retains_policy_evidence_and_leaves_slice_claimed(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result, adapter = self.check()
        run, proxy = result["run"], result["run"]["proxy"]
        self.assertEqual(run["state"], "claimed")
        self.assertEqual(proxy["state"], "proxy-check-passed")
        self.assertFalse(proxy["result"]["egress_enabled"])
        self.assertTrue(proxy["result"]["container_stopped"])
        self.assertEqual(adapter.calls, ["preflight", "start", "ready", "stop"])
        directory = self.store.root / "artifacts" / proxy["artifact_id"]
        policy = directory / "policy" / "proxy.json"
        self.assertEqual(json.loads(policy.read_bytes()), proxy_policy(self.profile))
        self.assertEqual(policy.stat().st_mode & 0o777, 0o444)
        self.assertEqual(proxy["policy_sha256"], digest(policy.read_bytes()))
        self.assertEqual(proxy["runtime_image"], self.profile["runtime"]["image"])
        self.assertEqual(proxy["bundle_sha256"], bundle_identity())
        evidence = json.loads((directory / "evidence.json").read_bytes())
        self.assertFalse(evidence["approved_external_access_qualified"])
        self.assertFalse(evidence["host_firewall_qualified"])
        self.assertEqual(proxy["result"]["evidence_sha256"], digest(canonical(evidence)))
        status = self.launcher.status("project", "feature")
        self.assertEqual(status["slices"]["01"]["proxy"], proxy)
        self.assertFalse(status["slices"]["02"]["eligible"])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_duplicate_check_returns_original_without_relaunch(self):
        authorization = self.authorize()
        adapter = FakeProxy()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            first = ProxyCheck(adapter).launch(session, "run-1")
            second = ProxyCheck(adapter).launch(session, "run-1")
        self.assertFalse(first["existing"])
        self.assertTrue(second["existing"])
        self.assertEqual(first["run"], second["run"])
        self.assertEqual(adapter.calls.count("start"), 1)

    def test_failures_stop_when_creation_was_attempted_and_never_pass(self):
        for mode, calls in (("preflight-fail", ["preflight"]), ("start-fail", ["preflight", "start", "stop"]),
                            ("timeout", ["preflight", "start", "ready", "stop"]),
                            ("readiness-fail", ["preflight", "start", "ready", "stop"])):
            with self.subTest(mode=mode):
                adapter = FakeProxy(mode)
                # Separate approved claims, not a reset of an interrupted run.
                feature = "feature-" + mode
                self.manifest["feature_id"] = feature
                self.save_manifest()
                authorization = self.authorize(feature)
                with self.launcher.coordinator("project", feature, "coordinator") as session:
                    session.claim("01", mode, authorization)
                    result = ProxyCheck(adapter).launch(session, mode)
                self.assertEqual(result["run"]["proxy"]["state"], "proxy-check-failed")
                self.assertTrue(result["run"]["proxy"]["result"]["container_stopped"])
                self.assertEqual(adapter.calls, calls)

    def test_unconfirmed_stop_and_interruption_require_deliberate_recovery(self):
        result, _ = self.check(FakeProxy("stop-fail"))
        self.assertEqual(result["run"]["proxy"]["state"], "proxy-held")
        self.assertFalse(result["run"]["proxy"]["result"]["container_stopped"])
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            for state in ("proxy-held", "preparing", "starting", "ready", "stopping"):
                with self.store.lock("ledger.lock"):
                    ledger = self.store.read()
                    ledger["runs"]["project/run-1"]["proxy"]["state"] = state
                    self.store.write(ledger)
                adapter = FakeProxy()
                self.expect_error("recovery_required", lambda: ProxyCheck(adapter).launch(session, "run-1"))
                self.assertEqual(adapter.calls, [])
                self.expect_error("recovery_required", lambda: Sandbox(fixtures.FakeCompose()).launch(session, "run-1"))

    def test_no_unclaimed_wrong_owner_or_closed_session_access(self):
        authorization = self.authorize()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.expect_error("unapproved", lambda: ProxyCheck(FakeProxy()).launch(session, "unknown"))
            session.claim("01", "run-1", authorization)
        self.expect_error("inactive_coordinator", lambda: ProxyCheck(FakeProxy()).launch(session, "run-1"))
        with self.launcher.coordinator("project", "feature", "other") as other:
            self.expect_error("unapproved", lambda: ProxyCheck(FakeProxy()).launch(other, "run-1"))

    def test_profile_drift_cannot_be_prepared(self):
        authorization = self.authorize()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            self.profile["network"]["allowed_domains"].append("evil.test")
            self.prepare_profile()
            self.expect_error("changed_input", lambda: ProxyCheck(FakeProxy()).launch(session, "run-1"))

    def test_check_uses_one_deadline_and_does_not_reset_consumed_slice_time(self):
        clock = [100]
        adapter = FakeProxy()
        original = adapter.preflight_proxy
        def late(*args):
            original(*args)
            clock[0] += 61
        adapter.preflight_proxy = late
        result, _ = self.check(adapter, lambda: clock[0])
        self.assertEqual(result["run"]["preparation_epoch"], 100)
        self.assertEqual(result["run"]["proxy"]["result"]["diagnostic"], "command_timeout")
        self.assertEqual(adapter.calls, ["preflight"])

    def test_baseline_after_offline_check_keeps_original_slice_deadline(self):
        self.profile["network"]["allowed_domains"] = []
        self.prepare_profile()
        authorization = self.authorize()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            ProxyCheck(FakeProxy(), clock=lambda: 100).launch(session, "run-1")
            adapter = fixtures.FakeCompose()
            result = Sandbox(adapter, export=fixtures.M2Tests.fake_export, clock=lambda: 110).launch(session, "run-1")
        self.assertEqual(result["run"]["preparation_epoch"], 100)
        self.assertEqual(adapter.context["deadline_epoch"], 3700)

    def test_proxy_check_does_not_enable_online_baseline(self):
        self.check()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            adapter = fixtures.FakeCompose()
            self.expect_error("policy_unavailable", lambda: Sandbox(adapter).launch(session, "run-1"))
            self.assertEqual(adapter.calls, [])

    def test_cli_only_accepts_a_run_id_not_policy_paths_or_activation_flags(self):
        # No live Docker calls: malformed requests fail before reaching the adapter.
        env = {**host_environment(), "XDG_STATE_HOME": str(self.base / "cli-state")}
        result = subprocess.run([sys.executable, "-B", str(ENTRY), "authorize", "--project", "project",
                                 "--feature", "feature", "--root", str(self.root)],
                                env=env, capture_output=True, text=True, check=True)
        authorization = json.loads(result.stdout)["authorization_id"]
        requests = [{"operation": "claim", "slice_id": "01", "run_id": "run-1", "authorization_id": authorization},
                    {"operation": "proxy-check", "run_id": "run-1", "policy": "/unapproved"},
                    {"operation": "proxy-check", "run_id": "run-1", "enable_egress": True},
                    {"operation": "status"}]
        result = subprocess.run([sys.executable, "-B", str(ENTRY), "coordinate", "--project", "project",
                                 "--feature", "feature", "--coordinator", "coordinator"],
                                input="\n".join(json.dumps(row) for row in requests) + "\n",
                                env=env, capture_output=True, text=True, check=True)
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([row["error"]["code"] for row in rows[2:4]], ["invalid_input", "invalid_input"])
        self.assertEqual(rows[-1]["slices"]["01"]["state"], "claimed")

    def test_cli_valid_request_uses_the_offline_lifecycle(self):
        from routine import cli
        authorization = self.authorize()
        requests = [{"operation": "claim", "slice_id": "01", "run_id": "run-1", "authorization_id": authorization},
                    {"operation": "proxy-check", "run_id": "run-1"}, {"operation": "status"}]
        adapter = FakeProxy()
        output = io.StringIO()
        with patch.object(cli, "Launcher", return_value=self.launcher), \
             patch("routine.proxy.ProxyCheck", return_value=ProxyCheck(adapter)), \
             patch.object(sys, "stdin", io.StringIO("\n".join(json.dumps(row) for row in requests) + "\n")), \
             redirect_stdout(output):
            self.assertEqual(cli.main(["coordinate", "--project", "project", "--feature", "feature",
                                       "--coordinator", "coordinator"]), 0)
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(rows[2]["run"]["proxy"]["state"], "proxy-check-passed")
        self.assertFalse(rows[-1]["slices"]["01"]["proxy"]["result"]["egress_enabled"])

    def test_adapter_preflight_checks_image_and_cgroups_without_requiring_writable_storage(self):
        calls = []
        def run(args, **limits):
            calls.append(args)
            if "image" in args:
                return canonical([{"Id": self.profile["runtime"]["image"], "Config": {"Labels": {
                    "routine.bundle-sha256": bundle_identity(), "routine.opencode-version": "2.0.22"}}}])
            if "ps" in args:
                return b""
            return canonical({**fixtures.supported_daemon(), "Driver": "overlayfs"})
        adapter = DockerCompose(run=run)
        adapter.preflight_proxy(self.profile, bundle_identity(), "a" * 64, 10)
        adapter.start_proxy(self.base, "a" * 64, 10)
        self.assertTrue(all(args[:3] == ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"] for args in calls))
        self.assertEqual(calls[-1][-6:], ["up", "--detach", "--no-build", "--pull", "never", "proxy"])
        self.assertFalse(any("network" in args for args in calls))
        self.expect_error("invalid_runtime", lambda: adapter.preflight_proxy(self.profile, "0" * 64, "a" * 64, 10))
        self.assertEqual(len(calls), 4)
        self.expect_error("invalid_runtime", lambda: DockerCompose(run=lambda *args, **kw: canonical(
            [{"Id": self.profile["runtime"]["image"], "Config": {"Labels": {}}}])).require_image(self.profile, bundle_identity(), 10))

    def test_effective_proxy_policy_mismatches_never_establish_readiness(self):
        artifact_id, policy_sha256 = "a" * 64, digest(canonical(proxy_policy(self.profile)))
        value = inspection(self.profile, artifact_id, policy_sha256)
        DockerCompose(run=lambda *args, **kw: canonical([value])).wait_proxy_ready(artifact_id, self.profile, policy_sha256, 10)
        mutations = [("HostConfig", "NetworkMode", "bridge"), ("HostConfig", "ReadonlyRootfs", False),
                     ("HostConfig", "Privileged", True), ("HostConfig", "CapAdd", ["NET_ADMIN"]),
                     ("HostConfig", "PortBindings", {"3128/tcp": [{"HostPort": "3128"}]}),
                     ("HostConfig", "Memory", 0), ("HostConfig", "MemorySwap", -1),
                     ("HostConfig", "PidsLimit", 0), ("HostConfig", "NanoCpus", 0),
                     ("Config", "User", "root"), ("Config", "Healthcheck", {"Test": ["CMD", "true"]}),
                     ("Config", "Labels", None), ("State", "Health", None)]
        for section, key, changed in mutations:
            bad = deepcopy(value)
            bad[section][key] = changed
            with self.subTest(section=section, key=key):
                self.expect_error("invalid_runtime", lambda: DockerCompose(run=lambda *args, **kw: canonical([bad])).wait_proxy_ready(
                    artifact_id, self.profile, policy_sha256, 10))
        for changed in ([], [{"Type": "bind", "Destination": "/policy/proxy.json", "RW": True}], None):
            bad = {**value, "Mounts": changed}
            self.expect_error("invalid_runtime", lambda: DockerCompose(run=lambda *args, **kw: canonical([bad])).wait_proxy_ready(
                artifact_id, self.profile, policy_sha256, 10))
        for field, changed in (("Image", "sha256:" + "0" * 64), ("Name", "/other"), ("HostConfig", None)):
            bad = {**value, field: changed}
            self.expect_error("invalid_runtime", lambda: DockerCompose(run=lambda *args, **kw: canonical([bad])).wait_proxy_ready(
                artifact_id, self.profile, policy_sha256, 10))

    def test_readiness_poll_and_late_response_share_one_deadline(self):
        artifact_id, policy_sha256 = "a" * 64, digest(canonical(proxy_policy(self.profile)))
        clock, calls = [0], []
        def run(args, **limits):
            calls.append(limits["timeout"])
            return canonical([inspection(self.profile, artifact_id, policy_sha256, "healthy" if len(calls) == 2 else "starting")])
        def sleep(seconds):
            clock[0] += seconds
        adapter = DockerCompose(run=run, sleep=sleep, monotonic=lambda: clock[0])
        adapter.wait_proxy_ready(artifact_id, self.profile, policy_sha256, 1)
        self.assertLess(calls[1], calls[0])
        def late(args, **limits):
            clock[0] += limits["timeout"]
            return canonical([inspection(self.profile, artifact_id, policy_sha256)])
        self.expect_error("command_timeout", lambda: DockerCompose(run=late, monotonic=lambda: clock[0]).wait_proxy_ready(
            artifact_id, self.profile, policy_sha256, 1))

    def test_unhealthy_stopped_and_never_ready_fail_with_bounded_diagnostics(self):
        artifact_id, policy_sha256 = "a" * 64, digest(canonical(proxy_policy(self.profile)))
        for status, running, code in (("unhealthy", True, "proxy_readiness_failed"), ("healthy", False, "proxy_start_failed"),
                                      ("unknown", True, "invalid_runtime")):
            value = inspection(self.profile, artifact_id, policy_sha256, status)
            value["State"]["Running"] = running
            self.expect_error(code, lambda: DockerCompose(run=lambda *args, **kw: canonical([value])).wait_proxy_ready(
                artifact_id, self.profile, policy_sha256, 10))
        clock = [0]
        def sleep(seconds):
            clock[0] += seconds
        value = inspection(self.profile, artifact_id, policy_sha256, "starting")
        self.expect_error("command_timeout", lambda: DockerCompose(run=lambda *args, **kw: canonical([value]),
            sleep=sleep, monotonic=lambda: clock[0]).wait_proxy_ready(artifact_id, self.profile, policy_sha256, 0.3))

    def test_stop_confirms_ownership_and_state_without_removing_anything(self):
        artifact_id, policy_sha256 = "a" * 64, digest(canonical(proxy_policy(self.profile)))
        value, calls = inspection(self.profile, artifact_id, policy_sha256), []
        def run(args, **limits):
            calls.append(args)
            if "stop" in args:
                value["State"]["Running"] = False
                return b""
            return canonical([value])
        DockerCompose(run=run).stop_proxy(self.base, artifact_id, 10)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[1][-4:], ["stop", "--timeout", "5", "proxy"])
        self.assertFalse(any(arg in ("down", "rm", "prune") for call in calls for arg in call))
        value["Name"] = "/other"
        calls.clear()
        self.expect_error("invalid_runtime", lambda: DockerCompose(run=run).stop_proxy(self.base, artifact_id, 10))
        self.assertEqual(len(calls), 1)

    def test_unexpected_interruption_after_creation_still_attempts_stop(self):
        authorization = self.authorize()
        adapter = FakeProxy()
        def interrupt(*args):
            adapter.calls.append("ready")
            raise SystemExit("Injected process interruption")
        adapter.wait_proxy_ready = interrupt
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            with self.assertRaises(SystemExit):
                ProxyCheck(adapter).launch(session, "run-1")
            self.assertEqual(adapter.calls[-1], "stop")
            self.expect_error("recovery_required", lambda: ProxyCheck(FakeProxy()).launch(session, "run-1"))

    def test_ledger_failure_during_stopping_does_not_skip_stop(self):
        authorization = self.authorize()
        adapter = FakeProxy()
        check = ProxyCheck(adapter)
        original = check.update
        def fail_stopping(session, run_key, **values):
            if values.get("state") == "stopping":
                raise OSError("private diagnostic canary")
            return original(session, run_key, **values)
        check.update = fail_stopping
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            result = check.launch(session, "run-1")
        self.assertEqual(adapter.calls[-1], "stop")
        self.assertEqual(result["run"]["proxy"]["state"], "proxy-check-failed")
        self.assertNotIn("private diagnostic canary", canonical(result).decode())

    def test_unsafe_artifact_parent_is_not_followed_for_evidence(self):
        outside = self.base / "outside"
        outside.mkdir()
        (self.store.root / "artifacts").symlink_to(outside, target_is_directory=True)
        result, adapter = self.check()
        self.assertEqual(result["run"]["proxy"]["state"], "proxy-check-failed")
        self.assertEqual(adapter.calls, [])
        self.assertEqual(list(outside.iterdir()), [])

    def test_existing_container_is_held_not_replaced_or_stopped(self):
        calls = []
        def run(args, **limits):
            calls.append(args)
            if "image" in args:
                return canonical([{"Id": self.profile["runtime"]["image"], "Config": {"Labels": {
                    "routine.bundle-sha256": bundle_identity(), "routine.opencode-version": "2.0.22"}}}])
            if "ps" in args:
                return b"existing-container-id\n"
            return canonical(fixtures.supported_daemon())
        result, _ = self.check(DockerCompose(run=run))
        self.assertEqual(result["run"]["proxy"]["state"], "proxy-held")
        self.assertEqual(result["run"]["proxy"]["result"]["diagnostic"], "recovery_required")
        self.assertFalse(result["run"]["proxy"]["result"]["container_stopped"])
        self.assertEqual(len(calls), 3)
        self.assertFalse(any("up" in args or "stop" in args for args in calls))

    @unittest.skipUnless(os.environ.get("OPENCODE_ROUTINE_COMPONENT_IMAGE"),
                         "Live offline lifecycle requires an explicitly approved pinned image and Docker access")
    def test_live_offline_proxy_lifecycle_retains_policy_and_confirmed_stopped_container(self):
        self.profile["runtime"]["image"] = os.environ["OPENCODE_ROUTINE_COMPONENT_IMAGE"]
        self.prepare_profile()
        retained = tempfile.mkdtemp(prefix="routine-m2-proxy-lifecycle-", dir="/tmp/opencode")
        self.store = Store(os.path.join(retained, "state"))
        self.launcher = Launcher(self.store)
        result, _ = self.check(DockerCompose(), run_id="probe-" + uuid.uuid4().hex)
        self.assertEqual(result["run"]["proxy"]["state"], "proxy-check-passed", result)
        self.assertTrue(result["run"]["proxy"]["result"]["container_stopped"])
        self.assertFalse(result["run"]["proxy"]["result"]["egress_enabled"])
        artifact_id = result["run"]["proxy"]["artifact_id"]
        value = DockerCompose().inspect_proxy(artifact_id, 10)
        self.assertFalse(value["State"]["Running"])
        self.assertEqual(value["HostConfig"]["NetworkMode"], "none")
        self.assertTrue((self.store.root / "artifacts" / artifact_id / "policy/proxy.json").is_file())
        self.retain_qualification(retained, result, value)

    def retain_qualification(self, retained, result, inspection):
        from pathlib import Path
        directory = Path(retained)
        retained_file(directory / "container-inspect.json", canonical(inspection), 0o600)
        qualification = {"version": 1, "run_id": result["run"]["request"]["run_id"],
                         "proxy": result["run"]["proxy"],
                         "host_assets": {name: digest((LIBRARY / "routine" / name).read_bytes()) for name in (
                             "proxy.py", "compose.py", "contracts.py", "launcher.py", "sandbox.py", "cli.py")},
                         "test_sha256": digest(Path(__file__).read_bytes()),
                         "approved_external_access_qualified": False, "host_firewall_qualified": False}
        retained_file(directory / "qualification.json", canonical(qualification), 0o600)

    @unittest.skipUnless(os.environ.get("OPENCODE_ROUTINE_COMPONENT_IMAGE"),
                         "Live offline negative test requires an explicitly approved pinned image and Docker access")
    def test_live_modified_policy_cannot_establish_readiness_and_container_is_stopped(self):
        class ModifiedPolicy(DockerCompose):
            def start_proxy(adapter, directory, artifact_id, timeout):
                path = directory / "policy/proxy.json"
                value = json.loads(path.read_bytes())
                value["allowed_domains"] = []
                path.chmod(0o600)
                path.write_bytes(canonical(value))
                path.chmod(0o444)
                super().start_proxy(directory, artifact_id, timeout)
        self.profile["runtime"]["image"] = os.environ["OPENCODE_ROUTINE_COMPONENT_IMAGE"]
        self.prepare_profile()
        retained = tempfile.mkdtemp(prefix="routine-m2-proxy-lifecycle-negative-", dir="/tmp/opencode")
        self.store = Store(os.path.join(retained, "state"))
        self.launcher = Launcher(self.store)
        result, _ = self.check(ModifiedPolicy(), run_id="probe-" + uuid.uuid4().hex)
        self.assertEqual(result["run"]["proxy"]["state"], "proxy-check-failed", result)
        self.assertEqual(result["run"]["proxy"]["result"]["diagnostic"], "proxy_readiness_failed")
        self.assertTrue(result["run"]["proxy"]["result"]["container_stopped"])
        value = DockerCompose().inspect_proxy(result["run"]["proxy"]["artifact_id"], 10)
        self.assertFalse(value["State"]["Running"])
        self.retain_qualification(retained, result, value)


if __name__ == "__main__":
    unittest.main()
