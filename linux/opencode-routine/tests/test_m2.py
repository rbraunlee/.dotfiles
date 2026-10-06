"""M2 contracts plus opt-in live Docker qualification; never fake isolation proof."""
from copy import deepcopy
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
import time
import unittest
from unittest.mock import patch
import uuid

import test_m1 as fixtures
from test_m1 import ENTRY, profile

from routine.compose import DockerCompose, bundle_identity, compose_document, offline_profile, read_evidence_archive, require_quota_backend, require_resource_support, worker_assets
from routine.contracts import RoutineError, canonical, digest, validate_profile
from routine.process import host_environment, run_bounded
from routine.sandbox import Sandbox
from routine.transfer import export_bundle


spec = importlib.util.spec_from_file_location("routine_worker", worker_assets() / "worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def supported_daemon():
    return {"Driver": "overlay2", "DriverStatus": [["Backing Filesystem", "xfs"]], "CgroupVersion": "2",
            **{key: True for key in ("MemoryLimit", "SwapLimit", "PidsLimit", "CpuCfsPeriod", "CpuCfsQuota")}}


class FakeCompose:
    """State-machine fake only; deliberately makes no isolation claims."""
    def __init__(self, mode="pass"):
        self.mode = mode
        self.calls = []
        self.context = None

    def preflight(self, profile, bundle_sha256, timeout):
        self.calls.append("preflight")
        if self.mode == "preflight-fail":
            raise RoutineError("adapter_failed", "Docker unavailable")

    def start(self, directory, artifact_id, timeout):
        self.calls.append("start")
        self.context = json.loads((directory / "handoff/context.json").read_bytes())
        if self.mode == "start-fail":
            raise RoutineError("adapter_failed", "Ambiguous create failure")
        if self.mode == "missing-container-id":
            return None
        return "d" * 64

    def wait(self, artifact_id, timeout):
        self.calls.append("wait")
        if self.mode == "timeout":
            raise RoutineError("command_timeout", "Fixture timeout")
        return 1 if self.mode == "check-fail" else 0

    def collect(self, artifact_id, max_bytes, timeout):
        self.calls.append("collect")
        context = self.context
        value = {"version": 2, **{key: context[key] for key in ("request", "baseline", "bundle_sha256", "profile_sha256", "input_bundle_sha256", "mounts")},
                 "outcome": "failed" if self.mode == "check-fail" else "passed",
                 "service": {"version": "2.0.22", "pid": 42, "hostname": "fixture", "uid": 10001, "location": "/control"},
                 "checks": [], "diagnostic": "required_command_failed" if self.mode == "check-fail" else None}
        commands = context["profile"]["commands"]
        work = [(f"setup-{index:02d}", "setup", entry) for index, entry in enumerate(commands["setup"], 1)]
        work += [(name, "check", entry) for name, entry in commands["checks"].items()]
        for name, stage, entry in work:
            value["checks"].append({"id": name, "stage": stage, "argv_sha256": digest(canonical(entry["argv"])),
                                    "shell_id": "sh_fixture", "status": "exited", "exit": 1 if self.mode == "check-fail" else 0,
                                    "output_sha256": digest(b"raw output is not exported"), "output_truncated": False})
        if self.mode == "missing-evidence":
            value["checks"] = []
        if self.mode == "forged-evidence":
            value["baseline"]["commit"] = "f" * 40
        if self.mode == "raw-output":
            value["checks"][0]["raw_output"] = "secret-canary"
        return value

    def stop(self, directory, artifact_id):
        self.calls.append("stop")
        if self.mode == "stop-fail":
            raise RoutineError("adapter_failed", "Stop unconfirmed")


class M2Tests(unittest.TestCase):
    # Reuse fixture infrastructure without re-running the inherited M1 test suite.
    write = fixtures.M1Tests.write
    fixture = fixtures.M1Tests.fixture
    save_manifest = fixtures.M1Tests.save_manifest
    authorize = fixtures.M1Tests.authorize
    expect_error = fixtures.M1Tests.expect_error

    def setUp(self):
        fixtures.M1Tests.setUp(self)
        self.profile = profile()
        self.profile.update(version=2, runtime={"image": "sha256:" + "c" * 64, "opencode_version": "2.0.22"})
        self.prepare_profile()
        self.empty_template = self.base / "empty-template"
        self.empty_template.mkdir()
        self.git("init", "-q", "--template=" + str(self.empty_template), str(self.root))
        self.write("README.md", b"# Independent fixture\n")
        self.git("-C", str(self.root), "add", "README.md")
        self.git("-C", str(self.root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                 "commit", "-q", "-m", "Fixture baseline")
        self.manifest["baseline"]["commit"] = self.git("-C", str(self.root), "rev-parse", "HEAD").decode().strip()
        self.save_manifest()
        # Read-only handoff files are deliberately retained by the launcher. Only
        # this disposable test fixture is made writable for TemporaryDirectory cleanup.
        self.addCleanup(self.writable_fixture)

    def writable_fixture(self):
        for path in self.base.rglob("*"):
            if path.is_dir() and not path.is_symlink():
                path.chmod(0o700)

    def prepare_profile(self):
        data = canonical(self.profile)
        self.write(".opencode/routine/project.json", data)
        self.manifest["profile_sha256"] = digest(data)
        self.manifest["bundle_sha256"] = bundle_identity()
        self.save_manifest()

    @staticmethod
    def git(*args):
        return run_bounded(["/usr/bin/git", *args], timeout=10)

    @staticmethod
    def fake_export(root, commit, destination, **limits):
        data = b"fixture Git bundle"
        Path(destination).write_bytes(data)
        return digest(data)

    def launch(self, adapter=None, export=None, run_id="run-1"):
        authorization = self.authorize()
        adapter = adapter or FakeCompose()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", run_id, authorization)
            result = Sandbox(adapter, export=export or self.fake_export).launch(session, run_id)
        return result, adapter

    def test_profile_v2_requires_immutable_image_and_pinned_v2_release(self):
        validate_profile(self.profile)
        for image, version in [("worker:latest", "2.0.22"), ("sha256:" + "c" * 64, "1.2.0"),
                               ("registry/worker@sha256:" + "c" * 64, "2.0.22")]:
            value = deepcopy(self.profile)
            value["runtime"] = {"image": image, "opencode_version": version}
            self.expect_error("invalid_profile", lambda: validate_profile(value))
        self.expect_error("runtime_missing", lambda: offline_profile(profile()))

    def test_network_services_and_credentials_fail_closed(self):
        for key, value in [("network", {"allowed_domains": ["example.com"]}),
                           ("services", [{"id": "database", "image": "postgres:fixture"}]),
                           ("credential_refs", ["model-access"]),
                           ("providers", [{"id": "openai", "credential_ref": "model-access"}])]:
            with self.subTest(key=key):
                value_profile = deepcopy(self.profile)
                value_profile[key] = value
                self.expect_error("policy_unavailable", lambda: offline_profile(value_profile))

    def test_compose_has_no_host_write_or_network_escape_surfaces(self):
        document = compose_document(self.profile, self.base / "handoff", "a" * 64)
        service = document["services"]["worker"]
        self.assertEqual(service["network_mode"], "none")
        self.assertEqual(service["cap_drop"], ["ALL"])
        self.assertEqual(service["user"], "10001:10001")
        self.assertEqual(service["environment"]["XDG_CONFIG_HOME"], "/opt/routine/config")
        self.assertEqual(service["storage_opt"]["size"], "1024M")
        self.assertEqual(service["mem_limit"], service["memswap_limit"])
        self.assertEqual(service["logging"]["options"]["max-file"], "1")
        self.assertEqual(service["logging"]["options"]["compress"], "false")
        self.assertEqual(len(service["volumes"]), 1)
        self.assertTrue(service["volumes"][0]["read_only"])
        self.assertEqual(service["volumes"][0]["target"], "/handoff")
        for key in ("ports", "devices", "pid", "ipc", "extra_hosts", "build"):
            self.assertNotIn(key, service)
        for forbidden in ("docker.sock", "SSH_AUTH_SOCK", "GITHUB_TOKEN", str(Path.home())):
            self.assertNotIn(forbidden, canonical(document).decode())

    def test_compose_json_is_accepted_without_daemon_access(self):
        path = self.base / "compose.json"
        path.write_bytes(canonical(compose_document(self.profile, self.base / "handoff", "a" * 64)))
        result = subprocess.run(["/usr/bin/docker", "compose", "--env-file", "/dev/null", "--file", str(path), "config", "--format", "json"],
                                env=host_environment(), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["services"]["worker"]["network_mode"], "none")

    def test_baseline_path_records_inputs_evidence_and_stopped_retained_container(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result, adapter = self.launch()
        run = result["run"]
        self.assertEqual(run["state"], "baseline-passed")
        self.assertTrue(run["result"]["container_stopped"])
        self.assertEqual(run["container_id"], "d" * 64)
        self.assertEqual(len(run["launch_id"]), 32)
        self.assertIsNone(run["result"]["diagnostic"])
        self.assertEqual(adapter.calls, ["preflight", "start", "wait", "collect", "stop"])
        directory = self.store.root / "artifacts" / run["artifact_id"]
        self.assertTrue((directory / "evidence.json").is_file())
        self.assertEqual(adapter.context["criteria"], ["AC-1"])
        self.assertIn(self.manifest["spec"]["path"], adapter.context["planning"])
        self.assertIn(self.manifest["tickets"][0]["path"], adapter.context["planning"])
        self.assertEqual((directory / "handoff/context.json").stat().st_mode & 0o777, 0o444)
        self.assertLessEqual(adapter.context["deadline_epoch"] - run["preparation_epoch"], 3600)
        self.assertFalse(self.launcher.status("project", "feature")["slices"]["02"]["eligible"])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_repeated_baseline_does_not_create_another_environment(self):
        authorization = self.authorize()
        adapter = FakeCompose()
        sandbox = Sandbox(adapter, export=self.fake_export)
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            first = sandbox.launch(session, "run-1")
            second = sandbox.launch(session, "run-1")
        self.assertFalse(first["existing"])
        self.assertTrue(second["existing"])
        self.assertEqual(first["run"], second["run"])
        self.assertEqual(adapter.calls.count("start"), 1)

    def test_preflight_failure_records_failure_without_dispatch(self):
        result, adapter = self.launch(FakeCompose("preflight-fail"))
        self.assertEqual(result["run"]["state"], "sandbox-failed")
        self.assertEqual(result["run"]["result"]["diagnostic"], "adapter_failed")
        self.assertEqual(adapter.calls, ["preflight"])

    def test_ambiguous_creation_failure_still_attempts_stop(self):
        result, adapter = self.launch(FakeCompose("start-fail"))
        self.assertEqual(result["run"]["state"], "sandbox-failed")
        self.assertEqual(adapter.calls, ["preflight", "start", "stop"])

    def test_missing_created_container_identity_cannot_record_a_running_or_passed_run(self):
        result, adapter = self.launch(FakeCompose("missing-container-id"))
        self.assertEqual(result["run"]["state"], "sandbox-failed")
        self.assertNotIn("container_id", result["run"])
        self.assertEqual(adapter.calls, ["preflight", "start", "stop"])

    def test_timeout_stops_without_marking_completion(self):
        result, adapter = self.launch(FakeCompose("timeout"))
        self.assertEqual(result["run"]["state"], "sandbox-failed")
        self.assertEqual(result["run"]["result"]["diagnostic"], "command_timeout")
        self.assertEqual(adapter.calls[-1], "stop")

    def test_failed_required_check_is_not_a_baseline_pass(self):
        result, _ = self.launch(FakeCompose("check-fail"))
        self.assertEqual(result["run"]["state"], "sandbox-failed")
        self.assertEqual(result["run"]["result"]["diagnostic"], "required_command_failed")
        self.assertIsNotNone(result["run"]["result"]["evidence_sha256"])

    def test_missing_evidence_cannot_pass(self):
        result, _ = self.launch(FakeCompose("missing-evidence"))
        self.assertEqual(result["run"]["state"], "sandbox-failed")
        self.assertIsNone(result["run"]["result"]["evidence_sha256"])

    def test_forged_evidence_cannot_pass(self):
        result, _ = self.launch(FakeCompose("forged-evidence"))
        self.assertEqual(result["run"]["state"], "sandbox-failed")
        self.assertEqual(result["run"]["result"]["diagnostic"], "invalid_evidence")

    def test_raw_secret_fields_are_rejected_not_regex_redacted(self):
        result, _ = self.launch(FakeCompose("raw-output"))
        self.assertEqual(result["run"]["state"], "sandbox-failed")
        self.assertNotIn("secret-canary", canonical(result).decode())
        self.assertFalse((self.store.root / "artifacts" / result["run"]["artifact_id"] / "evidence.json").exists())

    def test_unconfirmed_stop_holds_and_prevents_implicit_relaunch(self):
        result, _ = self.launch(FakeCompose("stop-fail"))
        self.assertEqual(result["run"]["state"], "sandbox-held")
        self.assertFalse(result["run"]["result"]["container_stopped"])
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.expect_error("recovery_required", lambda: Sandbox(FakeCompose(), self.fake_export).launch(session, "run-1"))

    def test_preparation_interruption_never_automatically_relaunches(self):
        authorization = self.authorize()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            Sandbox.update(session, "project/run-1", state="preparing")
            adapter = FakeCompose()
            self.expect_error("recovery_required", lambda: Sandbox(adapter, self.fake_export).launch(session, "run-1"))
            self.assertEqual(adapter.calls, [])

    def test_unclaimed_run_and_wrong_coordinator_cannot_launch(self):
        self.authorize()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.expect_error("unapproved", lambda: Sandbox(FakeCompose(), self.fake_export).launch(session, "run-1"))
            session.claim("01", "run-1", self.launcher.status("project", "feature")["authorization_id"])
        with self.launcher.coordinator("project", "feature", "other") as session:
            self.expect_error("unapproved", lambda: Sandbox(FakeCompose(), self.fake_export).launch(session, "run-1"))

    def test_export_ignores_malicious_hooks_config_and_fsmonitor(self):
        canary = self.base / "host-code-executed"
        hooks = self.root / ".git/hooks"
        hooks.mkdir(exist_ok=True)
        malicious = hooks / "post-checkout"
        malicious.write_text(f"#!/bin/sh\ntouch {canary}\n")
        malicious.chmod(0o755)
        fsmonitor = self.base / "malicious-fsmonitor"
        fsmonitor.write_text(f"#!/bin/sh\ntouch {canary}\nexit 1\n")
        fsmonitor.chmod(0o755)
        with (self.root / ".git/config").open("a") as config:
            config.write(f"\n[core]\n\tfsmonitor = {fsmonitor}\n[pack]\n\tpackObjectsHook = {fsmonitor}\n[include]\n\tpath = {fsmonitor}\n")
        destination = self.base / "repository.bundle"
        identity = export_bundle(self.root, self.manifest["baseline"]["commit"], destination, timeout=10, max_bytes=1024 * 1024)
        self.assertEqual(identity, digest(destination.read_bytes()))
        self.assertFalse(canary.exists())
        # Verify the export using another fresh bare Git directory; no checkout or
        # repository-provided code executes on the host in this test.
        bare = self.base / "verification.git"
        self.git("init", "--bare", "--template=" + str(self.empty_template), str(bare))
        self.git("--git-dir=" + str(bare), "bundle", "verify", str(destination))

    def test_export_rejects_alternates_and_missing_commit(self):
        info = self.root / ".git/objects/info"
        info.mkdir(exist_ok=True)
        (info / "alternates").write_text("/unapproved/objects\n")
        self.expect_error("unsafe_git", lambda: export_bundle(self.root, self.manifest["baseline"]["commit"], self.base / "bad.bundle", timeout=10, max_bytes=1024))
        (info / "alternates").unlink()
        self.expect_error("adapter_failed", lambda: export_bundle(self.root, "f" * 40, self.base / "missing.bundle", timeout=10, max_bytes=1024))

    def test_export_is_bounded_and_partial_bundle_is_not_dispatched(self):
        self.expect_error("output_limit", lambda: export_bundle(self.root, self.manifest["baseline"]["commit"], self.base / "partial.bundle", timeout=10, max_bytes=1))

    def test_process_timeout_and_output_limits_are_enforced(self):
        self.expect_error("command_timeout", lambda: run_bounded([sys.executable, "-c", "import time;time.sleep(10)"], timeout=0.05))
        self.expect_error("output_limit", lambda: run_bounded([sys.executable, "-c", "print('x'*1000)"], timeout=1, max_bytes=10))

    def test_dead_parent_cannot_leave_an_unbounded_pipe_holding_descendant(self):
        pid_file = self.base / "child.pid"
        script = ("import pathlib,subprocess,sys; "
                  "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); "
                  f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid))")
        self.expect_error("command_timeout", lambda: run_bounded([sys.executable, "-c", script], timeout=0.2))
        child = int(pid_file.read_text())
        status = Path(f"/proc/{child}/stat")

        def child_state():
            try:
                return status.read_text().split(") ", 1)[1].split()[0]
            except FileNotFoundError:
                return None

        try:
            # SIGKILL has been sent, but the kernel may not yet have scheduled the
            # descendant to finish exiting. Bound that transition, not its raw instant.
            deadline = time.monotonic() + 1
            while child_state() not in (None, "Z") and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertIn(child_state(), (None, "Z"))
        finally:
            if child_state() not in (None, "Z"):
                os.kill(child, signal.SIGKILL)

    def test_evidence_archive_rejects_links_traversal_multiple_and_oversized_files(self):
        def archive(names, link=False):
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode="w") as stream:
                for name in names:
                    member = tarfile.TarInfo(name)
                    data = b'{"version":1}'
                    member.size = len(data)
                    if link:
                        member.type = tarfile.SYMTYPE
                        member.linkname = "/etc/passwd"
                    stream.addfile(member, io.BytesIO(data) if not link else None)
            return buffer.getvalue()
        self.assertEqual(read_evidence_archive(archive(["evidence.json"]), 1024), {"version": 1})
        for names, link in [(["../evidence.json"], False), (["evidence.json"], True),
                            (["evidence.json", "extra.json"], False)]:
            self.expect_error("invalid_evidence", lambda: read_evidence_archive(archive(names, link), 1024))
        self.expect_error("invalid_evidence", lambda: read_evidence_archive(archive(["evidence.json"]), 1))

    def test_docker_adapter_never_uses_remote_context_or_pulls(self):
        calls = []
        artifact_id = "a" * 64
        document = compose_document(self.profile, self.base / "handoff", artifact_id)
        (self.base / "compose.json").write_bytes(canonical(document))
        def run(args, **limits):
            calls.append(args)
            if "image" in args:
                return canonical([{"Id": self.profile["runtime"]["image"], "Config": {"Labels": {
                    "routine.bundle-sha256": self.manifest["bundle_sha256"], "routine.opencode-version": "2.0.22"}}}])
            if "info" in args:
                return canonical(supported_daemon())
            if "inspect" in args:
                return canonical([{"Id": "d" * 64, "Name": "/routine-" + artifact_id[:32],
                                   "Image": self.profile["runtime"]["image"], "State": {"Running": False},
                                   "Config": {"Labels": document["services"]["worker"]["labels"]}}])
            return b""
        adapter = DockerCompose(run=run)
        adapter.preflight(self.profile, self.manifest["bundle_sha256"], 10)
        adapter.start(self.base, artifact_id, 10)
        self.assertTrue(all(args[:3] == ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"] for args in calls))
        creation = next(args for args in calls if "compose" in args)
        self.assertIn("--no-build", creation)
        self.assertIn("--no-recreate", creation)
        self.assertIn("never", creation)
        self.assertIn("/dev/null", creation)
        self.assertEqual(calls[-1][-2:], ["start", "d" * 64])

    def test_image_label_mismatch_is_rejected(self):
        def run(args, **limits):
            return canonical([{"Id": self.profile["runtime"]["image"], "Config": {"Labels": {}}}]) if "image" in args else canonical(supported_daemon())
        self.expect_error("invalid_runtime", lambda: DockerCompose(run=run).preflight(self.profile, self.manifest["bundle_sha256"], 10))

    def test_unqualified_quota_backend_is_rejected_before_image_or_container_operations(self):
        calls = []
        def run(args, **limits):
            calls.append(args)
            return canonical({"Driver": "overlayfs", "DriverStatus": [["driver-type", "io.containerd.snapshotter.v1"]]})
        self.expect_error("disk_quota_unavailable", lambda: DockerCompose(run=run).preflight(self.profile, self.manifest["bundle_sha256"], 10))
        self.assertEqual(len(calls), 1)
        self.assertIn("info", calls[0])
        self.expect_error("disk_quota_unavailable", lambda: require_quota_backend({"Driver": "overlay2", "DriverStatus": [["Backing Filesystem", "extfs"]]}))

    def test_missing_disabled_or_nonboolean_resource_support_prevents_dispatch(self):
        for key in ("MemoryLimit", "SwapLimit", "PidsLimit", "CpuCfsPeriod", "CpuCfsQuota"):
            for value in (None, False, 1):
                info = supported_daemon()
                info[key] = value
                with self.subTest(key=key, value=value):
                    self.expect_error("resource_limits_unavailable", lambda: require_resource_support(info))
        self.expect_error("resource_limits_unavailable", lambda: require_resource_support({**supported_daemon(), "CgroupVersion": "1"}))
        calls = []
        def run(args, **limits):
            calls.append(args)
            return canonical({**supported_daemon(), "SwapLimit": False})
        self.expect_error("resource_limits_unavailable", lambda: DockerCompose(run=run).preflight(self.profile, self.manifest["bundle_sha256"], 10))
        self.assertEqual(len(calls), 1)
        self.assertIn("info", calls[0])

    def test_worker_shell_request_is_quoted_and_raw_secret_output_not_exported(self):
        calls = []
        secret = "secret-canary-DO-NOT-EXPORT"
        def api(method, path, body=None):
            calls.append((method, path, body))
            if method == "post":
                return {"data": {"id": "sh_fixture", "status": "exited", "exit": 0}}
            return {"data": {"output": secret, "truncated": False}}
        baseline = worker.Baseline({"deadline_epoch": 100, "request": {"run_id": "fixture"}}, api=api, clock=lambda: 0)
        entry = {"argv": ["echo", "$(touch /host-canary)", "a b"], "timeout_seconds": 30}
        check = baseline.command("test", "check", entry)
        self.assertEqual(calls[0][2]["command"], "echo '$(touch /host-canary)' 'a b'")
        self.assertEqual(calls[0][2]["cwd"], "/home/worker/project")
        self.assertEqual(calls[0][2]["timeout"], 30000)
        self.assertNotIn(secret, canonical(check).decode())
        self.assertEqual(check["output_sha256"], digest(secret.encode()))

    def test_worker_reads_local_service_password_and_uses_environment_not_arguments(self):
        log = self.base / 'service.log'
        self.assertIsNone(worker.service_password(log))
        log.write_text('server listening on http://127.0.0.1:4096\nserver password private-test-password\n')
        password = worker.service_password(log)
        self.assertEqual(password, 'private-test-password')
        baseline = worker.Baseline({'deadline_epoch': 100, 'request': {'run_id': 'fixture'}}, clock=lambda: 0)
        with self.assertRaises(worker.WorkerFailure):
            baseline.call_api('get', '/api/info')
        baseline.password = password
        def run(args, **options):
            self.assertNotIn(password, ' '.join(args))
            self.assertEqual(options['env']['OPENCODE_PASSWORD'], password)
            options['stdout'].write(b'{"version":"2.0.22"}')
            return subprocess.CompletedProcess(args, 0)
        with patch.object(worker.subprocess, 'run', run):
            self.assertEqual(baseline.call_api('get', '/api/info'), {'version': '2.0.22'})

    def test_worker_command_deadline_cannot_be_extended_by_quiet_output(self):
        clock = [0]
        calls = []
        def api(method, path, body=None):
            calls.append((method, path))
            return None if method == "delete" else {"data": {"id": "sh_fixture", "status": "running"}}
        def sleep(seconds):
            clock[0] += seconds
        baseline = worker.Baseline({"deadline_epoch": 100, "request": {"run_id": "fixture"}}, api=api,
                                   clock=lambda: clock[0], sleep=sleep)
        check = baseline.command("test", "check", {"argv": ["quiet"], "timeout_seconds": 1})
        self.assertEqual(check["status"], "timeout")
        self.assertEqual(calls[-1][0], "delete")
        self.assertLess(clock[0], 2)

    def test_late_successful_api_response_cannot_pass_command_deadline(self):
        for late_phase in ("post", "get"):
            clock = [0]
            def api(method, path, body=None):
                if method == late_phase:
                    clock[0] = 2
                if method == "post":
                    return {"data": {"id": "sh_fixture", "status": "exited", "exit": 0}}
                return {"data": {"output": "late success", "truncated": False}}
            baseline = worker.Baseline({"deadline_epoch": 100, "request": {"run_id": "fixture"}}, api=api, clock=lambda: clock[0])
            check = baseline.command("test", "check", {"argv": ["quiet"], "timeout_seconds": 1})
            self.assertEqual(check["status"], "timeout")
            self.assertIsNone(check["exit"])
            self.assertEqual(check["output_sha256"], digest(b""))
            self.assertIsNone(baseline.operation_deadline)

    def test_hanging_api_client_obeys_command_budget_and_has_safe_diagnostic(self):
        baseline = worker.Baseline({"deadline_epoch": 100, "request": {"run_id": "fixture"}}, clock=lambda: 0)
        baseline.password = "private-test-password"
        def run(args, **options):
            self.assertLessEqual(options["timeout"], 1)
            raise subprocess.TimeoutExpired(args, options["timeout"])
        with patch.object(worker.subprocess, "run", run):
            with self.assertRaisesRegex(worker.WorkerFailure, "^command_timeout$"):
                baseline.command("test", "setup", {"argv": ["quiet"], "timeout_seconds": 1})
        self.assertIsNone(baseline.operation_deadline)

    def test_timed_out_poll_cancels_known_shell_in_bounded_cleanup_window(self):
        calls = []
        baseline = None
        def api(method, path, body=None):
            calls.append((method, path))
            if method == "post":
                return {"data": {"id": "sh_fixture", "status": "running"}}
            if method == "get":
                raise subprocess.TimeoutExpired("private-test-command", 1)
            self.assertEqual(baseline.operation_deadline, 2)
        baseline = worker.Baseline({"deadline_epoch": 100, "request": {"run_id": "fixture"}}, api=api, clock=lambda: 0)
        check = baseline.command("test", "setup", {"argv": ["quiet"], "timeout_seconds": 1})
        self.assertEqual(calls[-1], ("delete", "/api/shell/sh_fixture"))
        self.assertEqual(check["status"], "timeout")
        self.assertEqual(check["output_sha256"], digest(b""))
        self.assertIsNone(baseline.operation_deadline)
        self.assertIsNone(baseline.active_shell_id)

    def test_unconfirmed_api_cancellation_never_returns_a_pass(self):
        def api(method, path, body=None):
            if method == "post":
                return {"data": {"id": "sh_fixture", "status": "running"}}
            if method == "get":
                raise subprocess.TimeoutExpired("private-test-command", 1)
            raise worker.WorkerFailure("api_failed")
        baseline = worker.Baseline({"deadline_epoch": 100, "request": {"run_id": "fixture"}}, api=api, clock=lambda: 0)
        with self.assertRaisesRegex(worker.WorkerFailure, "^api_failed$"):
            baseline.command("test", "setup", {"argv": ["quiet"], "timeout_seconds": 1})
        self.assertIsNone(baseline.active_shell_id)

    def test_bundle_id_matches_actual_shipped_assets_and_cli(self):
        expected = digest(canonical({name: digest((worker_assets() / name).read_bytes())
                                     for name in ("Dockerfile", "worker.py", "opencode.json", "proxy.py")}))
        self.assertEqual(bundle_identity(), expected)
        result = subprocess.run([sys.executable, "-B", str(ENTRY), "bundle-id"],
                                env={**os.environ, "XDG_STATE_HOME": str(self.base / "read-only-operation")},
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["bundle_sha256"], expected)
        self.assertFalse((self.base / "read-only-operation").exists())

    @unittest.skipUnless(os.environ.get("OPENCODE_ROUTINE_TEST_IMAGE"),
                         "Live qualification requires an explicitly approved pinned worker image and Docker access")
    def test_live_container_baseline_and_locality_canaries(self):
        self.profile["runtime"]["image"] = os.environ["OPENCODE_ROUTINE_TEST_IMAGE"]
        host_canary = self.base / "host-only-canary"
        host_canary.write_text("host-only data")
        script = "\n".join([
            "import os,pathlib,socket",
            "assert os.geteuid()==10001",
            "assert pathlib.Path('/home/worker/project/.git').is_dir()",
            "assert not pathlib.Path('/home/worker/project/.git/objects/info/alternates').exists()",
            "assert not pathlib.Path('/var/run/docker.sock').exists()",
            "assert not os.access('/opt/routine/config', os.W_OK)",
            "assert not os.access('/control', os.W_OK)",
            f"assert not pathlib.Path({str(host_canary)!r}).exists()",
            "assert set(os.listdir('/sys/class/net')) == {'lo'}",
            "assert not pathlib.Path('/home/worker/repo-plugin-loaded').exists()",
            "pathlib.Path('tool-locality-canary').write_text(socket.gethostname())",
            "print('secret-canary-DO-NOT-EXPORT')",
        ])
        self.profile["commands"]["checks"] = {"isolation": {"argv": ["python3", "-c", script], "timeout_seconds": 30}}
        self.write(".opencode/plugins/evil.ts", b"await Bun.write('/home/worker/repo-plugin-loaded', 'unapproved plugin');\n")
        self.git("-C", str(self.root), "add", ".opencode/plugins/evil.ts")
        self.git("-C", str(self.root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                 "commit", "-q", "-m", "Add malicious discovery fixture")
        self.manifest["baseline"]["commit"] = self.git("-C", str(self.root), "rev-parse", "HEAD").decode().strip()
        self.prepare_profile()
        result, _ = self.launch(DockerCompose(), export_bundle, run_id="probe-" + uuid.uuid4().hex)
        self.assertEqual(result["run"]["state"], "baseline-passed", result)
        self.assertFalse((self.root / "tool-locality-canary").exists())
        self.assertNotIn("secret-canary-DO-NOT-EXPORT", (self.store.root / "artifacts" / result["run"]["artifact_id"] / "evidence.json").read_text())
        # The stopped container is intentionally retained, per the retention contract.


if __name__ == "__main__":
    unittest.main()
