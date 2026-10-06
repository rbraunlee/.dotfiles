"""Approved file snapshots; no live host-file bind mounts or isolation claims."""
from copy import deepcopy
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_m2 as fixtures
from routine.contracts import canonical, digest, validate_profile
from routine.inputs import describe_mounts, read_mount, stage_mounts
from routine.sandbox import validate_evidence


class ReadOnlyInputTests(unittest.TestCase):
    setUp = fixtures.M2Tests.setUp
    write = fixtures.M2Tests.write
    fixture = fixtures.M2Tests.fixture
    save_manifest = fixtures.M2Tests.save_manifest
    authorize = fixtures.M2Tests.authorize
    expect_error = fixtures.M2Tests.expect_error
    prepare_profile = fixtures.M2Tests.prepare_profile
    writable_fixture = fixtures.M2Tests.writable_fixture
    git = staticmethod(fixtures.M2Tests.git)
    fake_export = staticmethod(fixtures.M2Tests.fake_export)
    launch = fixtures.M2Tests.launch

    def approve_input(self, data=b"approved input", source="data/input.bin", target="/inputs/input.bin"):
        self.write(source, data)
        mount = {"source": source, "target": target, "read_only": True, "sha256": digest(data)}
        self.profile["mounts"].append(mount)
        self.prepare_profile()
        return mount

    def test_profile_requires_hash_and_rejects_writable_escape_or_overlapping_targets(self):
        mount = self.approve_input()
        validate_profile(self.profile)
        for edit in ({"target": "/inputs"}, {"target": "/inputs/../control"}, {"target": "/control/input"},
                     {"read_only": False}, {"sha256": "not-a-hash"}, {"source": "../host.txt"}):
            candidate = deepcopy(self.profile)
            candidate["mounts"][0].update(edit)
            with self.subTest(edit=edit), self.assertRaises(fixtures.RoutineError):
                validate_profile(candidate)
        candidate = deepcopy(self.profile)
        del candidate["mounts"][0]["sha256"]
        self.expect_error("invalid_input", lambda: validate_profile(candidate))
        for target in (mount["target"], mount["target"] + "/child", "/inputs/data"):
            candidate = deepcopy(self.profile)
            candidate["mounts"][0]["target"] = "/inputs/data/file" if target == "/inputs/data" else mount["target"]
            candidate["mounts"].append({**mount, "target": target})
            self.expect_error("invalid_profile", lambda: validate_profile(candidate))

    def test_authorization_retains_metadata_not_raw_input_and_drift_blocks_claim(self):
        secret = b"private-fixture-content-not-ledger-data"
        mount = self.approve_input(secret)
        authorization = self.authorize()
        package = self.store.read()["features"]["project/feature"]["package"]
        self.assertEqual(package["mounts"], [{**{key: mount[key] for key in ("source", "target", "sha256")},
                                             "size_bytes": len(secret)}])
        self.assertNotIn(secret.decode(), canonical(package).decode())
        self.write(mount["source"], b"unapproved replacement")
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.expect_error("changed_input", lambda: session.claim("01", "run-1", authorization))
        self.assertEqual(self.store.read()["runs"], {})

    def test_snapshot_copy_is_read_only_and_independent_of_live_source(self):
        mount = self.approve_input()
        result, adapter = self.launch()
        self.assertEqual(result["run"]["state"], "baseline-passed")
        directory = self.store.root / "artifacts" / result["run"]["artifact_id"]
        snapshot = directory / "handoff/mounts/0001.bin"
        self.assertEqual(snapshot.read_bytes(), b"approved input")
        self.assertEqual(snapshot.stat().st_mode & 0o777, 0o444)
        self.assertEqual(snapshot.parent.stat().st_mode & 0o777, 0o555)
        self.assertNotEqual(snapshot.stat().st_ino, (self.root / mount["source"]).stat().st_ino)
        self.write(mount["source"], b"changed after launch")
        self.assertEqual(snapshot.read_bytes(), b"approved input")
        document = fixtures.json.loads((directory / "compose.json").read_bytes())
        binding = document["services"]["worker"]["volumes"][1]
        self.assertEqual(binding["source"], str(snapshot))
        self.assertEqual(binding["target"], mount["target"])
        self.assertTrue(binding["read_only"])
        self.assertFalse(binding["bind"]["create_host_path"])
        self.assertEqual(result["run"]["mounts"], adapter.context["mounts"])

    def test_drift_during_preflight_aborts_before_export_or_start(self):
        mount = self.approve_input()
        class MutatingAdapter(fixtures.FakeCompose):
            def preflight(adapter, *args):
                super().preflight(*args)
                self.write(mount["source"], b"changed during preparation")
        adapter = MutatingAdapter()
        exports = []
        result, _ = self.launch(adapter, lambda *args, **kwargs: exports.append(args))
        self.assertEqual(result["run"]["result"]["diagnostic"], "changed_input")
        self.assertEqual(adapter.calls, ["preflight"])
        self.assertEqual(exports, [])

    def test_missing_or_wrong_hash_input_never_authorizes(self):
        mount = self.approve_input()
        self.write(mount["source"], b"hash mismatch")
        self.expect_error("changed_input", self.authorize)
        (self.root / mount["source"]).unlink()
        self.expect_error("missing_input", self.authorize)
        self.assertFalse((self.store.root / "ledger.json").exists())

    def test_non_regular_symlink_ancestor_and_hardlink_sources_rejected(self):
        mount = self.approve_input()
        source = self.root / mount["source"]
        source.unlink()
        os.mkfifo(source)
        self.expect_error("invalid_input", lambda: describe_mounts(self.root, [mount], 1024))
        source.unlink()
        outside = self.base / "outside.bin"
        outside.write_bytes(b"approved input")
        source.symlink_to(outside)
        self.expect_error("invalid_path", lambda: describe_mounts(self.root, [mount], 1024))
        source.unlink()
        os.link(outside, source)
        self.expect_error("invalid_input", lambda: describe_mounts(self.root, [mount], 1024))
        source.unlink()
        source.parent.rmdir()
        source.parent.symlink_to(self.base, target_is_directory=True)
        self.expect_error("invalid_path", lambda: describe_mounts(self.root, [mount], 1024))

    def test_directory_swap_to_symlink_cannot_redirect_open(self):
        mount = self.approve_input()
        directory = self.root / "data"
        original_open = os.open
        def swapping_open(path, *args, **kwargs):
            if path == "data":
                directory.rename(self.root / "original-data")
                directory.symlink_to(self.base, target_is_directory=True)
            return original_open(path, *args, **kwargs)
        with patch("routine.inputs.os.open", swapping_open):
            self.expect_error("invalid_path", lambda: describe_mounts(self.root, [mount], 1024))

    def test_empty_inputs_and_shared_total_byte_limit(self):
        mount = self.approve_input(b"")
        self.assertEqual(describe_mounts(self.root, [mount], 0)[0]["size_bytes"], 0)
        self.approve_input(b"abcd", "data/second", "/inputs/second")
        self.approve_input(b"efgh", "data/third", "/inputs/third")
        self.expect_error("input_limit", lambda: describe_mounts(self.root, self.profile["mounts"], 7))
        self.assertEqual(sum(record["size_bytes"] for record in describe_mounts(self.root, self.profile["mounts"], 8)), 8)

    def test_source_growth_and_copy_deadline_fail_closed(self):
        mount = self.approve_input(b"abc")
        calls = []
        def grow():
            calls.append(None)
            if len(calls) == 2:
                (self.root / mount["source"]).write_bytes(b"abc-too-large")
        self.expect_error("input_limit", lambda: read_mount(self.root, mount, 3, checkpoint=grow))
        self.write(mount["source"], b"abc")
        approved = describe_mounts(self.root, [mount], 3)
        handoff = self.base / "handoff"
        handoff.mkdir()
        def expired():
            raise fixtures.RoutineError("command_timeout", "Fixture timeout")
        self.expect_error("command_timeout", lambda: stage_mounts(self.root, [mount], approved, handoff, 3, expired))
        self.assertFalse((handoff / "mounts/0001.bin").exists())

    def test_authorization_hashing_is_deadline_bounded(self):
        mount = self.approve_input()
        with patch("routine.inputs.time.monotonic", side_effect=[0, 61]):
            self.expect_error("command_timeout", lambda: describe_mounts(self.root, [mount], 1024))

    def test_mounts_planning_and_bundle_share_preparation_byte_budget(self):
        self.approve_input(b"x" * (1024 * 1024))
        self.profile["resources"]["disk_mb"] = 1
        self.prepare_profile()
        result, adapter = self.launch()
        self.assertEqual(result["run"]["result"]["diagnostic"], "input_limit")
        self.assertEqual(adapter.calls, ["preflight"])

    def test_bundle_export_receives_only_remaining_budget(self):
        self.approve_input(b"x" * 100)
        limits = []
        def export(*args, **kwargs):
            limits.append(kwargs["max_bytes"])
            return self.fake_export(*args, **kwargs)
        result, adapter = self.launch(export=export)
        self.assertEqual(result["run"]["state"], "baseline-passed")
        self.assertEqual(limits, [1024 * 1024 * 1024 - 100 - len(canonical(adapter.context))])

    def test_oversized_export_cannot_bypass_combined_budget_or_start(self):
        self.approve_input(b"approved fixture")
        self.profile["resources"]["disk_mb"] = 1
        self.prepare_profile()
        def oversized_export(root, commit, destination, **limits):
            Path(destination).write_bytes(b"x" * (limits["max_bytes"] + 1))
            return "a" * 64
        result, adapter = self.launch(export=oversized_export)
        self.assertEqual(result["run"]["result"]["diagnostic"], "input_limit")
        self.assertEqual(adapter.calls, ["preflight"])

    def test_generated_snapshot_bind_configuration_parses_without_daemon(self):
        self.approve_input()
        result, _ = self.launch()
        compose = self.store.root / "artifacts" / result["run"]["artifact_id"] / "compose.json"
        parsed = fixtures.subprocess.run(["/usr/bin/docker", "compose", "--env-file", "/dev/null",
                                          "--file", str(compose), "config", "--format", "json"],
                                         env=fixtures.host_environment(), capture_output=True, text=True, timeout=15)
        self.assertEqual(parsed.returncode, 0, parsed.stderr)
        volumes = fixtures.json.loads(parsed.stdout)["services"]["worker"]["volumes"]
        snapshot_bind = next(volume for volume in volumes if volume["target"] == "/inputs/input.bin")
        self.assertTrue(snapshot_bind["read_only"])
        self.assertFalse(snapshot_bind["bind"]["create_host_path"])

    def test_missing_forged_raw_or_boolean_mount_evidence_cannot_pass(self):
        self.approve_input(b"x")
        result, adapter = self.launch()
        run = result["run"]
        package = self.store.read()["features"]["project/feature"]["package"]
        evidence = adapter.collect(run["artifact_id"], 1024 * 1024, 10)
        for edit in ("missing", "forged", "raw", "boolean", "legacy"):
            candidate = deepcopy(evidence)
            if edit == "missing":
                candidate["mounts"] = []
            elif edit == "forged":
                candidate["mounts"][0]["sha256"] = "f" * 64
            elif edit == "raw":
                candidate["mounts"][0]["data"] = "private-canary"
            elif edit == "boolean":
                candidate["mounts"][0]["size_bytes"] = True
            else:
                candidate["version"] = 1
                del candidate["mounts"]
            with self.subTest(edit=edit), self.assertRaises(fixtures.RoutineError):
                validate_evidence(candidate, run, package, run["input_bundle_sha256"])
        evidence.update(outcome="failed", diagnostic="input_snapshot_mismatch", mounts=[], service=None, checks=[])
        validate_evidence(evidence, run, package, run["input_bundle_sha256"])

    def worker_fixture(self):
        mount = self.approve_input()
        expected = describe_mounts(self.root, [mount], 1024)
        handoff, inputs = self.base / "handoff", self.base / "inputs"
        handoff.mkdir()
        inputs.mkdir()
        stage_mounts(self.root, [mount], expected, handoff, 1024)
        (inputs / "input.bin").write_bytes(b"approved input")
        context = {"profile": self.profile, "mounts": expected, "deadline_epoch": 100}
        baseline = fixtures.worker.Baseline(context, clock=lambda: 0)
        return context, baseline, handoff, inputs

    def test_worker_checks_both_locations_and_never_exports_raw_input(self):
        context, baseline, handoff, inputs = self.worker_fixture()
        records = []
        with patch.object(fixtures.worker.os, "statvfs", return_value=SimpleNamespace(f_flag=os.ST_RDONLY)):
            fixtures.worker.verify_mounts(context, baseline, records, handoff, inputs)
        self.assertEqual(records, context["mounts"])
        self.assertNotIn("approved input", canonical(records).decode())
        (inputs / "input.bin").write_bytes(b"bad replacement")
        with patch.object(fixtures.worker.os, "statvfs", return_value=SimpleNamespace(f_flag=os.ST_RDONLY)):
            with self.assertRaisesRegex(fixtures.worker.WorkerFailure, "input_snapshot_mismatch"):
                fixtures.worker.verify_mounts(context, baseline, [], handoff, inputs)

    def test_worker_rejects_missing_mapping_writable_target_and_modified_snapshot(self):
        context, baseline, handoff, inputs = self.worker_fixture()
        with patch.object(fixtures.worker.os, "statvfs", return_value=SimpleNamespace(f_flag=0)):
            with self.assertRaisesRegex(fixtures.worker.WorkerFailure, "input_snapshot_mismatch"):
                fixtures.worker.verify_mounts(context, baseline, [], handoff, inputs)
        with patch.object(fixtures.worker.os, "statvfs", return_value=SimpleNamespace(f_flag=os.ST_RDONLY)):
            candidate = deepcopy(context)
            candidate["mounts"] = []
            with self.assertRaisesRegex(fixtures.worker.WorkerFailure, "input_snapshot_mismatch"):
                fixtures.worker.verify_mounts(candidate, baseline, [], handoff, inputs)
            snapshot = handoff / "mounts/0001.bin"
            snapshot.chmod(0o600)
            snapshot.write_bytes(b"same-byte-size")
            with self.assertRaisesRegex(fixtures.worker.WorkerFailure, "input_snapshot_mismatch"):
                fixtures.worker.verify_mounts(context, baseline, [], handoff, inputs)


if __name__ == "__main__":
    unittest.main()
