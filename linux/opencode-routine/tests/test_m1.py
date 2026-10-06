"""Disposable fixtures only; no Docker, OpenCode service, Git hooks or live GitHub."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
LIBRARY = PACKAGE / ".local/lib/opencode-routine"
ENTRY = PACKAGE / ".local/bin/opencode-routine"
sys.path.insert(0, str(LIBRARY))

from routine.contracts import RoutineError, canonical, digest, parse_json, validate_profile
from routine.launcher import Launcher
from routine.store import Store


def profile():
    return {
        "version": 1,
        "commands": {"setup": [], "checks": {"test": {"argv": ["python3", "-m", "unittest"], "timeout_seconds": 30}}},
        "services": [], "mounts": [], "network": {"allowed_domains": []},
        "credential_refs": [], "providers": [],
        "resources": {"cpus": 1, "memory_mb": 512, "pids": 64, "disk_mb": 1024, "log_mb": 16, "command_seconds": 60},
        "budgets": {"slice_seconds": 3600, "inactivity_seconds": 600, "integration_seconds": 1800, "repairs": 2},
        "qa": {"kind": "none", "start": None},
    }


class M1Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="routine-m1-", dir="/tmp/opencode")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self.store = Store(self.base / "state")
        self.launcher = Launcher(self.store)
        self.manifest = self.fixture("feature")

    def write(self, path, data):
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)

    def fixture(self, feature):
        spec_path = f"planning/{feature}/spec.md"
        spec = b"# Fixture\n<!-- criterion: AC-1 -->\nFirst behavior.\n<!-- criterion: AC-2 -->\nConsumer behavior.\n"
        self.write(spec_path, spec)
        tickets = []
        for slice_id, criteria, dependencies in [("01", ["AC-1"], []), ("02", ["AC-2"], ["01"]), ("03", ["AC-1"], [])]:
            path = f"planning/{feature}/{slice_id}.md"
            data = f"# Slice {slice_id}\nImplement the explicitly mapped criteria.\n".encode()
            self.write(path, data)
            tickets.append({"slice_id": slice_id, "path": path, "sha256": digest(data),
                            "criteria": criteria, "dependencies": dependencies})
        profile_data = canonical(profile())
        self.write(".opencode/routine/project.json", profile_data)
        manifest = {"version": 1, "feature_id": feature,
                    "spec": {"path": spec_path, "sha256": digest(spec), "criteria": ["AC-1", "AC-2"]},
                    "tickets": tickets, "profile_sha256": digest(profile_data), "bundle_sha256": "b" * 64,
                    "baseline": {"commit": "a" * 40, "branch": f"refs/heads/features/{feature}"}}
        self.save_manifest(manifest)
        return manifest

    def save_manifest(self, manifest=None):
        manifest = manifest or self.manifest
        self.write(f".opencode/routine/features/{manifest['feature_id']}/approval.json", canonical(manifest))

    def authorize(self, feature="feature"):
        return self.launcher.authorize("project", feature, self.root)["authorization_id"]

    def expect_error(self, code, operation):
        with self.assertRaises(RoutineError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)

    def env(self):
        return {**os.environ, "XDG_STATE_HOME": str(self.base / "cli-state"), "PYTHONDONTWRITEBYTECODE": "1"}

    def test_authorization_and_claim_preserve_every_planning_byte(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        authorization = self.authorize()
        self.assertTrue(self.launcher.authorize("project", "feature", self.root)["existing"])
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            result = session.claim("01", "run-1", authorization)
            self.assertFalse(result["existing"])
            run = result["run"]
            self.assertEqual(run["state"], "claimed")
            self.assertEqual(run["criteria"], ["AC-1"])
            self.assertEqual(run["baseline"], self.manifest["baseline"])
            self.assertEqual(run["bundle_sha256"], "b" * 64)
            self.assertEqual(run["budgets"]["repairs"], 2)
            self.assertNotIn("started_at", run)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        restarted = Launcher(Store(self.store.root))
        status = restarted.status("project", "feature")
        self.assertEqual(status["slices"]["01"]["run_id"], "run-1")
        self.assertFalse(status["slices"]["02"]["eligible"])
        self.assertTrue(status["slices"]["03"]["eligible"])
        self.assertIsNone(status["coordinator"])

    def test_concurrent_duplicate_requests_create_exactly_one_claim(self):
        authorization = self.authorize()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            with ThreadPoolExecutor(max_workers=12) as pool:
                results = list(pool.map(lambda _: session.claim("01", "run-1", authorization), range(36)))
            self.assertEqual(sum(not result["existing"] for result in results), 1)
            self.expect_error("slice_claimed", lambda: session.claim("01", "run-2", authorization))
            self.expect_error("identity_conflict", lambda: session.claim("03", "run-1", authorization))
        self.assertEqual(len(self.store.read()["runs"]), 1)

    def test_duplicate_after_restart_returns_pinned_run(self):
        authorization = self.authorize()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            first = session.claim("01", "run-1", authorization)
        with Launcher(Store(self.store.root)).coordinator("project", "feature", "coordinator") as session:
            second = session.claim("01", "run-1", authorization)
        self.assertTrue(second["existing"])
        self.assertEqual(first["run"], second["run"])

    def test_unsatisfied_dependency_does_not_claim_an_alternative(self):
        authorization = self.authorize()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.expect_error("dependencies_unsatisfied", lambda: session.claim("02", "run-2", authorization))
        self.assertEqual(self.store.read()["runs"], {})
        self.assertTrue(self.launcher.status("project", "feature")["slices"]["01"]["eligible"])

    def test_claim_is_not_dependency_integration(self):
        authorization = self.authorize()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", "run-1", authorization)
            self.expect_error("dependencies_unsatisfied", lambda: session.claim("02", "run-2", authorization))

    def test_unapproved_feature_slice_and_authorization_rejected(self):
        self.expect_error("unapproved", lambda: self.launcher.status("project", "feature"))
        authorization = self.authorize()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.expect_error("unapproved", lambda: session.claim("missing", "run-1", authorization))
            self.expect_error("unapproved", lambda: session.claim("01", "run-1", "c" * 64))

    def test_closed_coordinator_cannot_claim(self):
        authorization = self.authorize()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            pass
        self.expect_error("inactive_coordinator", lambda: session.claim("01", "run-1", authorization))

    def test_same_feature_exclusion_and_independent_features(self):
        first = self.authorize()
        self.fixture("independent")
        second = self.authorize("independent")
        with self.launcher.coordinator("project", "feature", "first") as session:
            with self.assertRaises(RoutineError) as caught:
                with self.launcher.coordinator("project", "feature", "other"):
                    self.fail("Duplicate Coordinator admitted")
            self.assertEqual(caught.exception.code, "coordinator_busy")
            with self.launcher.coordinator("project", "independent", "second") as other:
                session.claim("01", "run-1", first)
                other.claim("01", "run-2", second)
        self.assertEqual(len(self.store.read()["runs"]), 2)

    def test_feature_id_and_project_id_cannot_be_rebound(self):
        self.authorize()
        self.manifest["bundle_sha256"] = "c" * 64
        self.save_manifest()
        self.expect_error("identity_conflict", self.authorize)
        new_root = self.base / "other-project"
        new_root.mkdir()
        original = self.root
        try:
            self.root = new_root
            self.fixture("other")
            self.expect_error("identity_conflict", lambda: self.launcher.authorize("project", "other", new_root))
        finally:
            self.root = original

    def test_changed_spec_ticket_profile_and_manifest_rejected(self):
        for path in [self.manifest["spec"]["path"], self.manifest["tickets"][0]["path"],
                     ".opencode/routine/project.json", ".opencode/routine/features/feature/approval.json"]:
            with self.subTest(path=path):
                authorization = self.authorize()
                original = (self.root / path).read_bytes()
                try:
                    with self.launcher.coordinator("project", "feature", "coordinator") as session:
                        self.write(path, original + b"\n")
                        self.expect_error("changed_input", lambda: session.claim("01", "run-1", authorization))
                finally:
                    self.write(path, original)
        self.assertEqual(self.store.read()["runs"], {})

    def test_updated_hashes_do_not_bypass_authorization(self):
        authorization = self.authorize()
        ticket = self.manifest["tickets"][0]
        data = b"# Changed scope\n"
        self.write(ticket["path"], data)
        ticket["sha256"] = digest(data)
        self.save_manifest()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.expect_error("changed_input", lambda: session.claim("01", "run-1", authorization))

    def test_cycles_and_missing_dependencies_rejected(self):
        for deps in [["02"], ["01"], ["missing"]]:
            with self.subTest(deps=deps):
                self.manifest["tickets"][0]["dependencies"] = deps
                self.save_manifest()
                self.expect_error("invalid_graph", self.authorize)

    def test_criteria_must_resolve_to_spec_markers(self):
        original = deepcopy(self.manifest)
        mutations = [lambda m: m["tickets"][0].update(criteria=["missing"]),
                     lambda m: m["tickets"][0].update(criteria=[]),
                     lambda m: m["spec"].update(criteria=["AC-1", "missing"])]
        for mutation in mutations:
            self.manifest = deepcopy(original)
            mutation(self.manifest)
            self.save_manifest()
            with self.assertRaises(RoutineError):
                self.authorize()

    def test_invalid_profiles_rejected(self):
        mutations = [lambda p: p["resources"].update(memory_mb=0),
                     lambda p: p["resources"].update(cpus=True),
                     lambda p: p["resources"].update(cpus=float("nan")),
                     lambda p: p["budgets"].update(repairs=3),
                     lambda p: p["commands"].update(checks={}),
                     lambda p: p["commands"]["checks"]["test"].update(timeout_seconds=61),
                     lambda p: p.update(providers=[{"id": "model", "credential_ref": "missing"}]),
                     lambda p: p["network"].update(allowed_domains=["127.0.0.1"]),
                     lambda p: p["network"].update(allowed_domains=["api.local"]),
                     lambda p: p["network"].update(allowed_domains=["*.example.com"]),
                     lambda p: p.update(mounts=[{"source": "/home", "target": "/inputs/home", "read_only": True}]),
                     lambda p: p.update(mounts=[{"source": "socket", "target": "/var/run/docker.sock", "read_only": True}]),
                     lambda p: p.update(mounts=[{"source": "data", "target": "/inputs/data", "read_only": False}]),
                     lambda p: p.update(secret="must-not-be-accepted")]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                value = profile()
                mutation(value)
                with self.assertRaises(RoutineError):
                    validate_profile(value)

    def test_unknown_manifest_fields_and_duplicate_json_keys_rejected(self):
        self.manifest["command"] = "arbitrary host script"
        self.save_manifest()
        self.expect_error("invalid_input", self.authorize)
        self.expect_error("invalid_json", lambda: parse_json(b'{"x":1,"x":2}'))
        self.expect_error("invalid_json", lambda: parse_json(b'{"x":NaN}'))

    def test_document_path_escape_and_symlinks_rejected(self):
        for path in ["../outside", "/etc/passwd", ".git/config", "planning//spec.md", "."]:
            self.manifest["spec"]["path"] = path
            self.save_manifest()
            self.expect_error("invalid_path", self.authorize)
        self.manifest["spec"]["path"] = "linked.md"
        (self.root / "linked.md").symlink_to(self.root / "planning/feature/spec.md")
        self.save_manifest()
        self.expect_error("invalid_path", self.authorize)

    def test_state_is_private_and_must_not_live_in_project(self):
        self.authorize()
        self.assertEqual(self.store.root.stat().st_mode & 0o777, 0o700)
        for name in ["ledger.lock", "ledger.json"]:
            self.assertEqual((self.store.root / name).stat().st_mode & 0o777, 0o600)
        unsafe = Launcher(Store(self.root / "state"))
        self.expect_error("unsafe_state", lambda: unsafe.authorize("project", "feature", self.root))
        self.store.root.chmod(0o755)
        self.expect_error("unsafe_state", lambda: Store(self.store.root))

    def test_symlink_and_hardlink_state_rejected(self):
        linked = self.base / "linked-state"
        linked.symlink_to(self.store.root, target_is_directory=True)
        self.expect_error("unsafe_state", lambda: Store(linked))
        self.authorize()
        os.link(self.store.root / "ledger.json", self.base / "ledger-link")
        self.expect_error("unsafe_state", lambda: self.launcher.status("project", "feature"))

    def test_dangling_ledger_symlink_is_not_an_empty_ledger(self):
        (self.store.root / "ledger.json").symlink_to(self.base / "missing-ledger")
        self.expect_error("unsafe_state", self.authorize)

    def test_invalid_typed_identifiers_rejected_without_claim(self):
        authorization = self.authorize()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            for value in (None, {}, [], 1, "../01", "", "x" * 65):
                with self.subTest(value=value):
                    self.expect_error("invalid_id", lambda: session.claim(value, "run-1", authorization))
            self.expect_error("invalid_input", lambda: session.claim("01", "run-1", {}))
        self.assertEqual(self.store.read()["runs"], {})

    def test_parallel_process_updates_do_not_clobber_independent_features(self):
        self.fixture("independent")
        self.authorize()
        self.authorize("independent")
        script = """
import sys
from routine.launcher import Launcher
from routine.store import Store
launcher = Launcher(Store(sys.argv[1]))
feature, run = sys.argv[2:4]
authorization = launcher.status('project', feature)['authorization_id']
with launcher.coordinator('project', feature, feature) as session:
    for _ in range(25):
        session.claim('01', run, authorization)
"""
        children = []
        try:
            for feature, run in [("feature", "first-run"), ("independent", "second-run")]:
                children.append(subprocess.Popen([sys.executable, "-c", script, str(self.store.root), feature, run],
                                                env={**os.environ, "PYTHONPATH": str(LIBRARY), "PYTHONDONTWRITEBYTECODE": "1"},
                                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            for child in children:
                stdout, stderr = child.communicate(timeout=10)
                self.assertEqual(child.returncode, 0, stdout + stderr)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.communicate()
        ledger = self.store.read()
        self.assertEqual(set(ledger["runs"]), {"project/first-run", "project/second-run"})
        for feature in ledger["features"].values():
            self.assertEqual(feature["slices"]["01"]["state"], "claimed")
            self.assertIsNone(feature["coordinator"])

    @unittest.skipUnless(shutil.which("stow"), "GNU Stow is not installed")
    def test_stow_package_links_only_runtime_files(self):
        target = self.base / "stow-home"
        target.mkdir()
        command = ["stow", "-t", str(target), "-d", str(PACKAGE.parent), PACKAGE.name]
        subprocess.run(command, capture_output=True, text=True, check=True)
        installed = target / ".local/bin/opencode-routine"
        self.assertTrue(installed.is_file())
        self.assertTrue(os.access(installed, os.X_OK))
        self.assertTrue((target / ".local/lib/opencode-routine/routine/launcher.py").is_file())
        self.assertFalse((target / "README.md").exists())
        self.assertFalse((target / "tests").exists())
        subprocess.run([str(installed), "--help"], capture_output=True, text=True, check=True)

    def test_cli_typed_protocol_and_no_host_commands(self):
        env = self.env()
        result = subprocess.run([sys.executable, str(ENTRY), "authorize", "--project", "project", "--feature", "feature", "--root", str(self.root)],
                                env=env, capture_output=True, text=True, check=True)
        authorization = json.loads(result.stdout)["authorization_id"]
        request = {"operation": "claim", "slice_id": "01", "run_id": "run-1", "authorization_id": authorization}
        requests = [request, request, {"operation": "status"}, {"operation": "launch", "command": "touch canary"},
                    {**request, "root": "/etc"}, ["not an object"]]
        result = subprocess.run([sys.executable, str(ENTRY), "coordinate", "--project", "project", "--feature", "feature", "--coordinator", "coordinator"],
                                env=env, input="\n".join(json.dumps(r) for r in requests) + "\n", capture_output=True, text=True, check=True)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(responses), 7)
        self.assertFalse(responses[1]["existing"])
        self.assertTrue(responses[2]["existing"])
        self.assertEqual(responses[4]["error"]["code"], "unsupported_operation")
        self.assertEqual(responses[5]["error"]["code"], "invalid_input")
        self.assertEqual(responses[6]["error"]["code"], "invalid_input")

    def test_process_lease_blocks_second_coordinator(self):
        self.authorize()
        env = {**os.environ, "XDG_STATE_HOME": str(self.base), "PYTHONDONTWRITEBYTECODE": "1"}
        # CLI default resolves <XDG_STATE_HOME>/opencode-routine; use that store here.
        self.launcher = Launcher(Store(self.base / "opencode-routine"))
        self.authorize()
        command = [sys.executable, str(ENTRY), "coordinate", "--project", "project", "--feature", "feature", "--coordinator", "first"]
        owner = subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(json.loads(owner.stdout.readline())["operation"], "coordinator_opened")
            other = subprocess.run(command[:-1] + ["second"], env=env, input="", capture_output=True, text=True, timeout=10)
            self.assertEqual(other.returncode, 1)
            self.assertEqual(json.loads(other.stdout)["error"]["code"], "coordinator_busy")
        finally:
            owner.communicate(timeout=10)
        self.assertIsNone(self.launcher.status("project", "feature")["coordinator"])

    def test_interrupted_atomic_claim_is_old_or_new_never_partial(self):
        authorization = self.authorize()
        for stage in ("before_replace", "after_replace", "after_directory_sync"):
            with self.subTest(stage=stage):
                state = self.base / stage
                launcher = Launcher(Store(state))
                launcher.authorize("project", "feature", self.root)
                script = """
import os, sys
from routine.launcher import Launcher
from routine.store import Store
store = Store(sys.argv[1])
launcher = Launcher(store)
with launcher.coordinator('project', 'feature', 'crashed') as session:
    def checkpoint(stage):
        if stage == sys.argv[2]:
            os._exit(42)
    store.checkpoint = checkpoint
    session.claim('01', 'run-1', sys.argv[3])
"""
                child = subprocess.run([sys.executable, "-c", script, str(state), stage, authorization],
                                       env={**os.environ, "PYTHONPATH": str(LIBRARY), "PYTHONDONTWRITEBYTECODE": "1"}, timeout=10)
                self.assertEqual(child.returncode, 42)
                ledger = Store(state).read()
                claimed = stage != "before_replace"
                self.assertEqual("project/run-1" in ledger["runs"], claimed)
                self.assertEqual(ledger["features"]["project/feature"]["slices"]["01"]["state"], "claimed" if claimed else "pending")
                # Kernel lock was released, but persisted interruption must be recovered deliberately.
                with self.assertRaises(RoutineError) as caught:
                    with launcher.coordinator("project", "feature", "replacement"):
                        self.fail("Implicit recovery admitted")
                self.assertEqual(caught.exception.code, "recovery_required")


if __name__ == "__main__":
    unittest.main()
