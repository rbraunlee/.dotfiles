"""Gated M2 environment compiler/lifecycle; no Docker/network/credential access."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import unittest
from unittest.mock import patch

import test_m2 as fixtures
from test_m2_proxy_lifecycle import LIMITS
from routine.contracts import RoutineError, canonical, digest, validate_profile
from routine.environment import Environment
from routine.policy import environment_policy, allows_flow
from routine.credentials import CredentialBroker, CredentialFiles
from routine.sandbox import Sandbox


def environment_profile():
    value = fixtures.profile()
    value.update(version=3, runtime={"image": "sha256:" + "c" * 64, "opencode_version": "2.0.22"})
    value["network"] = {"allowed_domains": ["api.example.com"], "proxy": deepcopy(LIMITS), "dns_servers": ["8.8.8.8"]}
    value["services"] = [{"id": "database", "image": "sha256:" + "d" * 64, "user": "10002:10002",
                          "ports": [5432], "readiness": {"argv": ["/probe", "--ready"], "timeout_seconds": 5},
                          "resources": deepcopy(value["resources"]), "tmpfs": [{"target": "/data", "size_mb": 16}]}]
    value["credential_refs"] = ["database-access", "model-access"]
    value["providers"] = [{"id": "openai", "credential_ref": "model-access", "domains": ["api.example.com"]}]
    value["credential_bindings"] = [
        {"ref": "database-access", "consumer": "service:database", "purpose": "development", "max_bytes": 128},
        {"ref": "model-access", "consumer": "provider:openai", "purpose": "model", "max_bytes": 128}]
    return value


class FakeBroker(CredentialBroker):
    def __init__(self, mode="pass"):
        self.mode, self.calls, self.buffers = mode, [], []

    def resolve(self, request, binding, timeout=None):
        self.calls.append((request["authorization_id"], binding["ref"], binding["consumer"]))
        if self.mode == "fail" and len(self.calls) == 2:
            raise OSError("private-secret-diagnostic")
        value = bytearray(b"fake-secret-DO-NOT-EXPORT" if self.mode != "oversized" else b"x" * 129)
        self.buffers.append(value)
        return value


class FakeEnvironment:
    def __init__(self, mode="pass"):
        self.mode, self.calls = mode, []

    def call(self, name):
        self.calls.append(name)
        if self.mode == name:
            raise RoutineError("adapter_failed", "Fixture operation failed")

    def preflight(self, plan, timeout):
        self.call("preflight")

    def create_networks(self, plan, timeout):
        self.call("networks")

    def enforce_policy(self, plan, timeout):
        self.call("firewall")

    def start_component(self, plan, component, credentials, timeout):
        self.call("start:" + component)
        self.credentials = credentials

    def wait_ready(self, plan, component, timeout):
        self.call("ready:" + component)

    def stop_components(self, plan, components, timeout):
        self.calls.append("stop:" + ",".join(components))
        return self.mode != "stop-fail"


class EnvironmentTests(unittest.TestCase):
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
        self.profile = environment_profile()
        self.prepare_profile()

    def plan(self):
        return environment_policy(self.profile, "a" * 64)

    def test_v3_profile_preserves_old_versions_and_requires_complete_contracts(self):
        validate_profile(self.profile)
        validate_profile(fixtures.profile())
        for section, key, value in (("network", "dns_servers", ["127.0.0.1"]),
                                    ("network", "dns_servers", ["::1"]),
                                    ("network", "dns_servers", ["192.0.0.9"]),
                                    ("network", "dns_servers", ["8.8.8.8", "8.8.8.8"])):
            bad = deepcopy(self.profile)
            bad[section][key] = value
            self.expect_error("invalid_profile", lambda: validate_profile(bad))
        for key, value in (("image", "database:latest"), ("user", "0:0"), ("ports", [True]),
                           ("ports", [65536]), ("ports", [5432, 5432]),
                           ("tmpfs", [{"target": "/run/credentials", "size_mb": 16}])):
            bad = deepcopy(self.profile)
            bad["services"][0][key] = value
            self.expect_error("invalid_profile", lambda: validate_profile(bad))
        bad = deepcopy(self.profile)
        bad["services"][0]["privileged"] = True
        self.expect_error("invalid_input", lambda: validate_profile(bad))

    def test_bindings_reject_unknown_consumers_production_and_privilege_widening(self):
        for key, value in (("ref", "unknown"), ("consumer", "service:unknown"), ("consumer", "host"),
                           ("purpose", "production"), ("purpose", "model"), ("max_bytes", True),
                           ("max_bytes", 65537)):
            bad = deepcopy(self.profile)
            bad["credential_bindings"][0][key] = value
            self.expect_error("invalid_profile", lambda: validate_profile(bad))
        for key, value in (("path", "/home/user/token"), ("value", "private-secret"), ("environment", "GITHUB_TOKEN")):
            bad = deepcopy(self.profile)
            bad["credential_bindings"][0][key] = value
            self.expect_error("invalid_input", lambda: validate_profile(bad))
        bad = deepcopy(self.profile)
        bad["providers"][0]["domains"] = ["unapproved.example"]
        self.expect_error("invalid_profile", lambda: validate_profile(bad))
        bad = deepcopy(self.profile)
        bad["credential_bindings"] = []
        self.expect_error("invalid_profile", lambda: validate_profile(bad))

    def test_compiler_is_deterministic_scoped_and_secret_free(self):
        plan = self.plan()
        self.assertEqual(plan, self.plan())
        self.assertFalse(plan["activation_enabled"])
        self.assertTrue(plan["constraints"]["services_read_only_root"])
        self.assertFalse(plan["constraints"]["inherit_host_credentials"])
        self.assertEqual(plan["networks"][0]["members"], ["worker", "proxy", "service:database"])
        self.assertEqual(plan["networks"][1]["members"], ["proxy"])
        self.assertTrue(plan["networks"][0]["internal"])
        self.assertNotEqual(plan["networks"], environment_policy(self.profile, "b" * 64)["networks"])
        self.assertEqual(plan["credentials"][0]["target"], "/run/credentials/service/database/database-access")
        self.assertIn("encrypted_routing", plan["open_gates"])
        self.assertNotIn("private-secret", canonical(plan).decode())

    def test_flow_policy_allows_only_explicit_worker_services_and_proxy_routes(self):
        plan = self.plan()
        for source, destination, protocol, port in (("worker", "proxy", "tcp", 3128),
                ("worker", "service:database", "tcp", 5432), ("proxy", "8.8.8.8", "udp", 53),
                ("proxy", "8.8.8.8", "tcp", 53), ("proxy", "1.1.1.1", "tcp", 443)):
            self.assertTrue(allows_flow(plan, source, destination, protocol, port))
        for source, destination, protocol, port in (("worker", "8.8.8.8", "tcp", 443),
                ("worker", "8.8.8.8", "udp", 53), ("worker", "proxy", "tcp", 80),
                ("worker", "service:database", "tcp", 80), ("service:database", "8.8.8.8", "tcp", 443),
                ("service:database", "worker", "tcp", 4096), ("proxy", "10.0.0.1", "tcp", 443),
                ("proxy", "192.168.1.1", "tcp", 443), ("proxy", "169.254.169.254", "tcp", 443),
                ("proxy", "192.0.0.9", "tcp", 443), ("proxy", "::ffff:8.8.8.8", "tcp", 443),
                ("proxy", "2606:4700:4700::1111", "tcp", 443), ("proxy", "host", "tcp", 443),
                ("worker", "other-slice:service", "tcp", 5432), ("worker", "proxy", "udp", 3128)):
            self.assertFalse(allows_flow(plan, source, destination, protocol, port))
        self.assertFalse(allows_flow(plan, "worker", "proxy", "tcp", True))
        self.assertEqual(plan["firewall"]["dns"]["worker"], "local-service-names-only-no-forwarding")
        # Transport eligibility is not authorization of encrypted application routing.
        self.assertFalse(plan["activation_enabled"])

    def test_no_egress_profile_omits_unnecessary_proxy_and_external_network(self):
        self.profile["network"]["allowed_domains"] = []
        self.profile["network"]["dns_servers"] = []
        self.profile["providers"] = []
        self.profile["credential_refs"] = ["database-access"]
        self.profile["credential_bindings"] = self.profile["credential_bindings"][:1]
        plan = self.plan()
        self.assertEqual(len(plan["networks"]), 1)
        self.assertNotIn("proxy", plan["components"])
        self.assertFalse(allows_flow(plan, "worker", "proxy", "tcp", 3128))

    def test_credential_files_are_consumer_scoped_and_never_export_values_or_hashes(self):
        broker = FakeBroker()
        files = CredentialFiles(self.base / "credentials", broker)
        request = {"authorization_id": "a" * 64}
        bindings = self.plan()["credentials"]
        metadata = files.stage(request, bindings, checkpoint=lambda: None, max_bytes=1024)
        for binding in metadata:
            path = files.path(binding)
            self.assertEqual(path.read_bytes(), b"fake-secret-DO-NOT-EXPORT")
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)
        self.assertNotIn("fake-secret", canonical(metadata).decode())
        self.assertNotIn("sha256", canonical(metadata).decode())
        self.assertTrue(all(not any(buffer) for buffer in broker.buffers))
        self.assertEqual(len(broker.calls), 2)
        files.cleanup()
        self.assertFalse(any(path.is_file() for path in (self.base / "credentials").rglob("*")))

    def test_credential_failures_and_oversized_values_erase_only_owned_files(self):
        for mode in ("fail", "oversized"):
            broker = FakeBroker(mode)
            root = self.base / ("credentials-" + mode)
            files = CredentialFiles(root, broker)
            with self.assertRaises((RoutineError, OSError)):
                files.stage({"authorization_id": "a" * 64}, self.plan()["credentials"], checkpoint=lambda: None, max_bytes=1024)
            self.assertFalse(any(path.is_file() for path in root.rglob("*")))
            self.assertTrue(all(not any(buffer) for buffer in broker.buffers))
        self.expect_error("policy_unavailable", lambda: CredentialBroker().resolve({}, self.plan()["credentials"][0]))

    def test_plan_is_durable_idempotent_and_does_not_launch_or_unblock(self):
        authorization = self.authorize()
        before = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            first = Environment().prepare(session, "run-1")
            second = Environment().prepare(session, "run-1")
        self.assertFalse(first["existing"])
        self.assertTrue(second["existing"])
        self.assertEqual(first["run"], second["run"])
        record = first["run"]["environment"]
        self.assertEqual(record["state"], "planned")
        self.assertEqual(first["run"]["state"], "claimed")
        directory = self.store.root / "artifacts" / record["artifact_id"]
        self.assertEqual(digest((directory / "plan.json").read_bytes()), record["plan_sha256"])
        self.assertEqual((directory / "plan.json").stat().st_mode & 0o777, 0o600)
        status = self.launcher.status("project", "feature")
        self.assertEqual(status["slices"]["01"]["environment"], record)
        self.assertFalse(status["slices"]["02"]["eligible"])
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()})

    def test_real_adapter_is_unconditionally_gated_before_networks_or_credential_reads(self):
        authorization = self.authorize()
        broker = FakeBroker()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            environment = Environment(broker=broker)
            environment.prepare(session, "run-1")
            result = environment.launch(session, "run-1")
            self.assertEqual(result["run"]["environment"]["state"], "environment-blocked")
            self.assertEqual(result["run"]["environment"]["result"]["diagnostic"], "policy_unavailable")
            self.assertFalse(result["run"]["environment"]["result"]["effects_attempted"])
            self.assertEqual(broker.calls, [])
            self.assertTrue(environment.launch(session, "run-1")["existing"])

    def run_fake(self, mode="pass", broker=None):
        authorization = self.authorize()
        adapter = FakeEnvironment(mode)
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            environment = Environment(adapter=adapter, broker=broker or FakeBroker())
            environment.prepare(session, "run-1")
            result = environment.launch(session, "run-1")
        return result, adapter

    def test_lifecycle_enforces_firewall_before_workloads_and_stops_reverse_order(self):
        result, adapter = self.run_fake()
        self.assertEqual(adapter.calls, ["preflight", "networks", "firewall", "start:proxy", "ready:proxy",
                                        "start:service:database", "ready:service:database", "stop:service:database,proxy"])
        self.assertEqual(result["run"]["environment"]["state"], "environment-check-passed")
        self.assertFalse(result["run"]["environment"]["result"]["qualified"])
        directory = self.store.root / "artifacts" / result["run"]["environment"]["artifact_id"]
        self.assertFalse(any(path.is_file() for path in (directory / "credentials").rglob("*")))
        self.assertNotIn("fake-secret", canonical(result).decode())

    def test_failed_start_still_stops_ambiguous_component_and_exports_only_codes(self):
        result, adapter = self.run_fake("start:service:database")
        self.assertEqual(adapter.calls[-1], "stop:service:database,proxy")
        self.assertEqual(result["run"]["environment"]["state"], "environment-check-failed")
        self.assertEqual(result["run"]["environment"]["result"]["diagnostic"], "adapter_failed")

    def test_firewall_failure_cannot_read_credentials_or_start_components(self):
        broker = FakeBroker()
        result, adapter = self.run_fake("firewall", broker)
        self.assertEqual(result["run"]["environment"]["state"], "environment-check-failed")
        self.assertEqual(broker.calls, [])
        self.assertFalse(any(name.startswith("start:") for name in adapter.calls))

    def test_uncertain_stop_retains_private_credentials_and_blocks_relaunch(self):
        result, adapter = self.run_fake("stop-fail")
        self.assertEqual(result["run"]["environment"]["state"], "environment-held")
        directory = self.store.root / "artifacts" / result["run"]["environment"]["artifact_id"]
        self.assertTrue(any(path.is_file() for path in (directory / "credentials").rglob("*")))
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.expect_error("recovery_required", lambda: Environment(adapter=adapter).launch(session, "run-1"))
            self.expect_error("recovery_required", lambda: Sandbox(fixtures.FakeCompose()).launch(session, "run-1"))

    def test_input_and_plan_drift_stop_before_runtime_side_effects(self):
        authorization = self.authorize()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            environment = Environment(adapter=FakeEnvironment(), broker=FakeBroker())
            result = environment.prepare(session, "run-1")
            path = self.store.root / "artifacts" / result["run"]["environment"]["artifact_id"] / "plan.json"
            path.write_bytes(b"{}")
            self.expect_error("changed_input", lambda: environment.launch(session, "run-1"))
            self.assertEqual(environment.adapter.calls, [])

    def test_profile_drift_is_rejected_even_when_declared_hashes_are_updated(self):
        authorization = self.authorize()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            environment = Environment(adapter=FakeEnvironment())
            environment.prepare(session, "run-1")
            self.profile["services"][0]["ports"].append(5433)
            self.prepare_profile()
            self.expect_error("changed_input", lambda: environment.launch(session, "run-1"))
            self.assertEqual(environment.adapter.calls, [])

    def test_credentials_are_not_read_for_providers_or_shared_with_proxy(self):
        broker = FakeBroker()
        result, adapter = self.run_fake(broker=broker)
        self.assertEqual([call[1] for call in broker.calls], ["database-access"])
        self.assertEqual([binding["consumer"] for binding in adapter.credentials], ["service:database"])
        self.assertNotIn("fake-secret", canonical(result).decode())

    def test_broker_timeout_wipes_returned_buffer_before_writing(self):
        clock = [0]
        class LateBroker(FakeBroker):
            def resolve(broker, request, binding, timeout=None):
                value = super().resolve(request, binding, timeout)
                clock[0] += 6
                return value
        broker = LateBroker()
        files = CredentialFiles(self.base / "late-credentials", broker, clock=lambda: clock[0])
        self.expect_error("command_timeout", lambda: files.stage({"authorization_id": "a" * 64}, self.plan()["credentials"],
            checkpoint=lambda: 5, max_bytes=1024))
        self.assertTrue(all(not any(buffer) for buffer in broker.buffers))
        self.assertFalse(any(path.is_file() for path in files.root.rglob("*")))

    def test_credential_cleanup_refuses_replaced_files_without_deleting_foreign_work(self):
        files = CredentialFiles(self.base / "owned-credentials", FakeBroker())
        bindings = files.stage({"authorization_id": "a" * 64}, self.plan()["credentials"][:1],
                               checkpoint=lambda: None, max_bytes=1024)
        path = files.path(bindings[0])
        path.rename(files.root / "original-inode")
        path.write_bytes(b"foreign-work")
        self.expect_error("unsafe_state", files.cleanup)
        self.assertEqual(path.read_bytes(), b"foreign-work")

    def test_combined_plan_and_credential_reservation_is_bounded_before_preparation(self):
        self.profile["resources"]["disk_mb"] = 1
        refs = ["model-access", "database-access"] + [f"extra-{index}" for index in range(14)]
        self.profile["credential_refs"] = refs
        self.profile["credential_bindings"] = [{"ref": ref, "consumer": "provider:openai" if ref == "model-access" else "service:database",
            "purpose": "model" if ref == "model-access" else "development", "max_bytes": 65536} for ref in refs]
        self.prepare_profile()
        authorization = self.authorize()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            self.expect_error("input_limit", lambda: Environment().prepare(session, "run-1"))
        self.assertNotIn("environment", self.store.read()["runs"]["project/run-1"])

    def test_command_timeouts_fail_late_success_and_preserve_consumed_slice_budget(self):
        authorization = self.authorize()
        clock = [100]
        adapter, broker = FakeEnvironment(), FakeBroker()
        original = adapter.wait_ready
        def late(plan, component, timeout):
            original(plan, component, timeout)
            if component == "service:database":
                clock[0] += timeout
        adapter.wait_ready = late
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            environment = Environment(adapter, broker, clock=lambda: clock[0])
            environment.prepare(session, "run-1")
            clock[0] = 110
            result = environment.launch(session, "run-1")
            self.assertEqual(result["run"]["preparation_epoch"], 100)
            self.assertEqual(result["run"]["environment"]["result"]["diagnostic"], "command_timeout")
            self.assertEqual(adapter.calls[-1], "stop:service:database,proxy")
            self.assertTrue(environment.launch(session, "run-1")["existing"])

    def test_expired_preparation_budget_cannot_be_reset_by_check(self):
        authorization = self.authorize()
        clock = [100]
        adapter = FakeEnvironment()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            environment = Environment(adapter, clock=lambda: clock[0])
            environment.prepare(session, "run-1")
            clock[0] = 3700
            self.expect_error("command_timeout", lambda: environment.launch(session, "run-1"))
            self.assertEqual(adapter.calls, [])

    def test_interruption_after_creation_stops_components_but_requires_recovery(self):
        authorization = self.authorize()
        adapter = FakeEnvironment()
        def interrupt(*args):
            raise SystemExit("Injected interruption")
        adapter.wait_ready = interrupt
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            environment = Environment(adapter, FakeBroker())
            environment.prepare(session, "run-1")
            with self.assertRaises(SystemExit):
                environment.launch(session, "run-1")
            self.assertEqual(adapter.calls[-1], "stop:proxy")
            self.expect_error("recovery_required", lambda: environment.launch(session, "run-1"))

    def test_ledger_write_failure_during_stop_never_skips_component_stopping(self):
        authorization = self.authorize()
        adapter = FakeEnvironment()
        environment = Environment(adapter, FakeBroker())
        original = environment.update
        def fail_stopping(session, run_key, **values):
            if values.get("state") == "stopping":
                raise OSError("private-diagnostic")
            return original(session, run_key, **values)
        environment.update = fail_stopping
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            environment.prepare(session, "run-1")
            result = environment.launch(session, "run-1")
        self.assertEqual(adapter.calls[-1], "stop:service:database,proxy")
        self.assertEqual(result["run"]["environment"]["state"], "environment-check-failed")
        self.assertNotIn("private-diagnostic", canonical(result).decode())

    def test_unrecognized_broker_error_codes_cannot_export_secret_diagnostics(self):
        class MaliciousBroker(FakeBroker):
            def resolve(broker, *args):
                raise RoutineError("private-secret-diagnostic", "private-secret-message")
        result, _ = self.run_fake(broker=MaliciousBroker())
        self.assertEqual(result["run"]["environment"]["result"]["diagnostic"], "adapter_failed")
        self.assertNotIn("private-secret", canonical(result).decode())

    def test_unclaimed_wrong_owner_and_closed_sessions_cannot_prepare_or_launch(self):
        authorization = self.authorize()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.expect_error("unapproved", lambda: Environment().prepare(session, "missing"))
            session.claim("01", "run-1", authorization)
            Environment().prepare(session, "run-1")
        self.expect_error("inactive_coordinator", lambda: Environment().launch(session, "run-1"))
        with self.launcher.coordinator("project", "feature", "other") as other:
            self.expect_error("unapproved", lambda: Environment().prepare(other, "run-1"))
            self.expect_error("unapproved", lambda: Environment().launch(other, "run-1"))

    def test_cli_cannot_supply_network_fragments_credentials_or_activation_overrides(self):
        from routine import cli
        authorization = self.authorize()
        requests = [{"operation": "claim", "slice_id": "01", "run_id": "run-1", "authorization_id": authorization},
                    {"operation": "environment-plan", "run_id": "run-1", "network": "unapproved"},
                    {"operation": "environment-plan", "run_id": "run-1"},
                    {"operation": "environment-check", "run_id": "run-1", "enable_egress": True},
                    {"operation": "environment-check", "run_id": "run-1"}, {"operation": "status"}]
        output = io.StringIO()
        with patch.object(cli, "Launcher", return_value=self.launcher), \
             patch.object(cli.sys, "stdin", io.StringIO("\n".join(json.dumps(row) for row in requests) + "\n")), \
             redirect_stdout(output):
            self.assertEqual(cli.main(["coordinate", "--project", "project", "--feature", "feature", "--coordinator", "coordinator"]), 0)
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(rows[2]["error"]["code"], "invalid_input")
        self.assertEqual(rows[4]["error"]["code"], "invalid_input")
        self.assertEqual(rows[5]["run"]["environment"]["state"], "environment-blocked")
        self.assertFalse(rows[-1]["slices"]["02"]["eligible"])
        self.assertEqual(rows[-1]["slices"]["01"]["state"], "claimed")

    def test_profiles_cannot_override_host_qualification_gates(self):
        for section in (None, "network"):
            bad = deepcopy(self.profile)
            target = bad if section is None else bad[section]
            target["activation_enabled"] = True
            self.expect_error("invalid_input", lambda: validate_profile(bad))

    def test_environment_operations_share_the_baseline_and_proxy_lock(self):
        authorization = self.authorize()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            with self.store.lock("sandbox-" + digest(b"project/run-1") + ".lock"):
                self.expect_error("coordinator_busy", lambda: Environment().prepare(session, "run-1"))
            Environment().prepare(session, "run-1")
            with self.store.lock("sandbox-" + digest(b"project/run-1") + ".lock"):
                self.expect_error("coordinator_busy", lambda: Environment().launch(session, "run-1"))

    def test_service_readiness_storage_and_proxy_policy_limits_fail_closed(self):
        for mounts in ([{"target": "/data", "size_mb": 1025}],
                       [{"target": "/data", "size_mb": 1}, {"target": "/data/sub", "size_mb": 1}],
                       [{"target": "/data\0bad", "size_mb": 1}],
                       [{"target": "/", "size_mb": 1}]):
            bad = deepcopy(self.profile)
            bad["services"][0]["tmpfs"] = mounts
            self.expect_error("invalid_profile", lambda: validate_profile(bad))
        bad = deepcopy(self.profile)
        bad["services"][0]["readiness"]["timeout_seconds"] = 61
        self.expect_error("invalid_profile", lambda: validate_profile(bad))
        bad = deepcopy(self.profile)
        bad["network"]["allowed_domains"] = [f"api-{index}.example.com" for index in range(4000)]
        self.expect_error("invalid_profile", lambda: validate_profile(bad))


if __name__ == "__main__":
    unittest.main()
