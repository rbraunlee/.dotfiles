"""Builder-owned W1 contracts; disposable local fixtures, never runtime qualification."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1]
LIBRARY = PACKAGE / ".local/lib/opencode-routine"
ENTRY = PACKAGE / ".local/bin/opencode-routine"
sys.path.insert(0, str(LIBRARY))

from routine.contracts import RoutineError
from routine.launcher import Launcher
from routine.store import Store


def canonical(value):
    """Independent oracle for the documented canonical inventory identity."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


class W1Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="routine-w1-", dir="/tmp/opencode")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.bundle = self.base / "bundle"
        for name, data in {
            "agents/orchestrator.md": b"# Trusted fixture orchestrator\n",
            "agents/builder.md": b"# Builder owns tests\n",
            "skills/tdd/SKILL.md": b"# Fixture TDD\n",
            "skills/tdd/resources/check.md": b"Fixture resource\n",
            "provenance.md": b"# Locally owned disposable fixture\n",
        }.items():
            self.write_at(self.bundle / name, data)
        self.inventory = [{"path": p.relative_to(self.bundle).as_posix(), "sha256": digest(p.read_bytes())}
                          for p in sorted(self.bundle.rglob("*")) if p.is_file()]
        self.bundle_sha256 = digest(canonical(self.inventory))
        self.api = self.base / "reviewed-api.json"
        self.api.write_bytes(b'{"openapi":"3.1.0","info":{"version":"fixture"}}\n')
        self.configuration = self.base / "reviewed-configuration.json"
        self.configuration.write_bytes(b'{"fixture":"reviewed, not executable"}\n')
        self.git("init", "--initial-branch=main")
        self.write_at(self.root / "README.md", b"Disposable W1 baseline\n")
        self.git("add", "README.md")
        self.git("-c", "user.name=W1 Fixture", "-c", "user.email=w1@example.invalid",
                 "commit", "-m", "Disposable fixture baseline")
        self.commit = self.git("rev-parse", "HEAD").strip()
        self.profile = self.local_profile()
        self.manifest = self.fixture("feature")
        self.evidence = self.fixture_evidence()
        self.store = Store(self.base / "state")
        self.launcher = Launcher(self.store)

    @staticmethod
    def write_at(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def env(self, state=None):
        # No ambient Git, OpenCode, authentication or user configuration in children.
        return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.home / "config"),
                "XDG_DATA_HOME": str(self.home / "data"),
                "XDG_STATE_HOME": str(state or self.base / "cli-state"),
                "PYTHONPATH": str(LIBRARY), "PYTHONDONTWRITEBYTECODE": "1",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}

    def git(self, *args):
        result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args],
                                cwd=self.root, env=self.env(), capture_output=True,
                                text=True, check=True, timeout=10)
        return result.stdout

    def local_profile(self):
        return {
            "version": 4, "execution": "trusted-local",
            "commands": {"setup": [], "checks": {
                "test": {"argv": ["python3", "-m", "unittest"], "timeout_seconds": 30}}},
            "command_limits": {"command_seconds": 60, "input_bytes": 1048576, "output_bytes": 65536},
            "budgets": {"slice_seconds": 3600, "inactivity_seconds": 600,
                        "integration_seconds": 1800, "repairs": 2},
            "concurrency": {"workers_per_feature": 3}, "credential_refs": ["fixture-model"],
            "runtime": {"opencode_version": "2.0.22", "api_sha256": digest(self.api.read_bytes()),
                        "configuration_sha256": digest(self.configuration.read_bytes()),
                        "connection_ref": "fixture-service"},
            "services": [], "qa": {"kind": "none", "start": None},
        }

    def fixture(self, feature):
        spec = b"# Fixture\n<!-- criterion: AC-1 -->\nOwner.\n<!-- criterion: AC-2 -->\nConsumer.\n"
        spec_path = f"planning/{feature}/spec.md"
        self.write_at(self.root / spec_path, spec)
        tickets = []
        for slice_id, criteria, dependencies in [("01", ["AC-1"], []),
                                                 ("02", ["AC-2"], ["01"]),
                                                 ("03", ["AC-1"], [])]:
            path = f"planning/{feature}/{slice_id}.md"
            data = f"# Slice {slice_id}\nImplement mapped criteria only.\n".encode()
            self.write_at(self.root / path, data)
            tickets.append({"slice_id": slice_id, "path": path, "sha256": digest(data),
                            "criteria": criteria, "dependencies": dependencies})
        profile_bytes = canonical(self.profile)
        self.write_at(self.root / ".opencode/routine/project.json", profile_bytes)
        branch = f"refs/heads/features/{feature}"
        self.git("update-ref", branch, self.commit)
        manifest = {"version": 2, "execution": "trusted-local", "feature_id": feature,
                    "spec": {"path": spec_path, "sha256": digest(spec), "criteria": ["AC-1", "AC-2"]},
                    "tickets": tickets, "profile_sha256": digest(profile_bytes),
                    "bundle_sha256": self.bundle_sha256,
                    "baseline": {"commit": self.commit, "branch": branch}}
        self.save_manifest(manifest)
        return manifest

    def save_manifest(self, manifest=None):
        manifest = self.manifest if manifest is None else manifest
        self.write_at(self.root / f".opencode/routine/features/{manifest['feature_id']}/approval.json",
                      canonical(manifest))

    def save_profile(self):
        data = canonical(self.profile)
        self.write_at(self.root / ".opencode/routine/project.json", data)
        self.manifest["profile_sha256"] = digest(data)
        self.save_manifest()
        self.evidence["profile_sha256"] = digest(data)

    def fixture_evidence(self, manifest=None):
        manifest = self.manifest if manifest is None else manifest
        return {"version": 1, "execution": "trusted-local", "baseline": deepcopy(manifest["baseline"]),
                "profile_sha256": manifest["profile_sha256"], "mutations_approved": True,
                "checks": {"test": {"outcome": "passed", "evidence_ref": "baseline-check"}}}

    def authorize(self, launcher=None, feature="feature", evidence=None):
        return (launcher or self.launcher).authorize_local(
            "project", feature, self.root, self.bundle, self.api, self.configuration,
            self.evidence if evidence is None else evidence)

    def dispatch(self, authorization, slice_id="01", dispatch_id="dispatch-1", launcher=None,
                 feature="feature"):
        return (launcher or self.launcher).authorize_local_dispatch(
            "project", feature, slice_id, dispatch_id, authorization)

    def approved(self, slice_id="01", dispatch_id="dispatch-1"):
        authorization = self.authorize()["authorization_id"]
        self.dispatch(authorization, slice_id, dispatch_id)
        return authorization

    def claim(self, session, authorization, slice_id="01", run_id="run-1", dispatch_id="dispatch-1",
              baseline=None):
        return session.claim_local(slice_id, run_id, authorization, dispatch_id,
                                   self.manifest["baseline"] if baseline is None else baseline)

    def rejected(self, operation, code=None):
        with self.assertRaises(RoutineError) as caught:
            operation()
        if code is not None:
            self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_authorization_and_dispatch_are_explicit_and_idempotent(self):
        result = self.authorize()
        self.assertFalse(result["existing"])
        self.assertTrue(self.authorize()["existing"])
        dispatch = self.dispatch(result["authorization_id"])
        self.assertEqual(dispatch["dispatch_id"], "dispatch-1")
        self.assertRegex(dispatch["dispatch_authorization_id"], r"^[0-9a-f]{64}$")
        self.assertFalse(dispatch["existing"])
        self.assertTrue(self.dispatch(result["authorization_id"])["existing"])

    def test_claim_freezes_planning_and_has_no_execution_timer_or_effects(self):
        before = {p.relative_to(self.root).as_posix(): p.read_bytes()
                  for p in self.root.rglob("*") if p.is_file()}
        authorization = self.approved()
        feature = self.store.read()["features"]["project/feature"]
        self.assertEqual(feature["schema_version"], 1)
        self.assertEqual(feature["execution"], "trusted-local")
        self.assertEqual(feature["verified_head"], self.manifest["baseline"])
        self.assertEqual(feature["fixture_evidence"], self.evidence)
        snapshot = feature["bundle_snapshot"]
        self.assertEqual(snapshot["sha256"], self.bundle_sha256)
        self.assertEqual(snapshot["inventory"], self.inventory)
        self.assertTrue(Path(snapshot["path"]).is_relative_to(self.store.root))
        self.assertFalse(Path(snapshot["path"]).is_relative_to(self.root))
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            result = self.claim(session, authorization)
            run = result["run"]
            self.assertFalse(result["existing"])
            self.assertEqual(run["schema_version"], 1)
            self.assertEqual(run["execution"], "trusted-local")
            self.assertEqual(run["state"], "claimed")
            self.assertEqual(run["baseline"], self.manifest["baseline"])
            self.assertEqual(run["criteria"], ["AC-1"])
            self.assertEqual(run["budgets"], self.profile["budgets"])
            self.assertEqual(run["command_limits"], self.profile["command_limits"])
            self.assertEqual(run["credential_refs"], self.profile["credential_refs"])
            self.assertEqual(run["bundle_sha256"], self.bundle_sha256)
            self.assertEqual(run["bundle_snapshot"], snapshot)
            self.assertEqual(run["profile_sha256"], self.manifest["profile_sha256"])
            self.assertEqual(run["spec_sha256"], self.manifest["spec"]["sha256"])
            self.assertEqual(run["ticket_sha256"], self.manifest["tickets"][0]["sha256"])
            self.assertEqual(run["request"]["dispatch_id"], "dispatch-1")
            self.assertEqual(run["request"]["dispatch_authorization_id"],
                             feature["dispatches"]["dispatch-1"]["dispatch_authorization_id"])
            self.assertEqual(run["request"]["execution"], "trusted-local")
            self.assertEqual(run["request"]["baseline"], self.manifest["baseline"])
            for key in ("started_at", "runtime_started_at", "inactivity_started_at", "deadline",
                        "session_id", "checkout", "environment"):
                self.assertNotIn(key, run)
        self.assertEqual(before, {p.relative_to(self.root).as_posix(): p.read_bytes()
                                  for p in self.root.rglob("*") if p.is_file()})
        status = self.launcher.status("project", "feature")
        self.assertEqual(status["execution"], "trusted-local")
        self.assertEqual(status["verified_head"], self.manifest["baseline"])
        self.assertEqual(status["slices"]["01"]["run_id"], "run-1")
        self.assertEqual(status["slices"]["02"]["waiting_for"], ["01"])
        self.assertIn("dispatches", status)

    def test_planning_byte_drift_and_rehashed_scope_cannot_change_authority(self):
        authorization = self.approved()
        paths = [self.manifest["spec"]["path"], self.manifest["tickets"][0]["path"],
                 ".opencode/routine/project.json", ".opencode/routine/features/feature/approval.json"]
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            for name in paths:
                with self.subTest(name=name):
                    path = self.root / name
                    original = path.read_bytes()
                    try:
                        path.write_bytes(original + b"\n")
                        before = self.store.read()
                        self.rejected(lambda: self.claim(session, authorization))
                        self.assertEqual(before, self.store.read())
                    finally:
                        path.write_bytes(original)
            ticket = self.manifest["tickets"][0]
            self.write_at(self.root / ticket["path"], b"# Expanded scope\n")
            ticket["sha256"] = digest((self.root / ticket["path"]).read_bytes())
            self.save_manifest()
            self.rejected(lambda: self.claim(session, authorization))
        self.assertEqual(self.store.read()["runs"], {})
        self.rejected(self.authorize)

    def test_invalid_graph_and_missing_required_criterion_reject_authorization(self):
        original = deepcopy(self.manifest)
        mutations = [lambda m: m["tickets"][0].update(dependencies=["02"]),
                     lambda m: m["tickets"][0].update(dependencies=["01"]),
                     lambda m: m["tickets"][0].update(dependencies=["missing"]),
                     lambda m: m["tickets"][0].update(criteria=[]),
                     lambda m: m["tickets"][0].update(criteria=["missing"]),
                     lambda m: m["spec"].update(criteria=["AC-1", "missing"])]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                self.manifest = deepcopy(original)
                mutation(self.manifest)
                self.save_manifest()
                self.rejected(self.authorize)
                self.assertEqual(self.store.read()["features"], {})

    def test_local_profile_rejects_sandbox_fields_and_unapproved_local_capabilities(self):
        original = deepcopy(self.profile)
        mutations = [lambda p: p.update(version=3),
                     lambda p: p.update(execution="sandbox"),
                     lambda p: p.update(resources={"cpus": 1}),
                     lambda p: p.update(mounts=[]),
                     lambda p: p.update(providers=[]),
                     lambda p: p.update(services=[{"id": "database"}]),
                     lambda p: p.update(qa={"kind": "web", "start": ["server"]}),
                     lambda p: p["commands"].update(checks={}),
                     lambda p: p["commands"]["checks"]["test"].update(timeout_seconds=61),
                     lambda p: p["commands"]["checks"]["test"].update(env={"SECRET": "canary"}),
                     lambda p: p["command_limits"].update(input_bytes=0),
                     lambda p: p["command_limits"].update(output_bytes=True),
                     lambda p: p["budgets"].update(repairs=3),
                     lambda p: p["concurrency"].update(workers_per_feature=0),
                     lambda p: p["runtime"].update(configuration_sha256="invalid")]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                self.profile = deepcopy(original)
                mutation(self.profile)
                self.save_profile()
                self.rejected(self.authorize)
                self.assertEqual(self.store.read()["features"], {})

    def test_fixture_evidence_requires_approved_mutations_exact_baseline_and_all_checks(self):
        mutations = [lambda e: e.update(mutations_approved=False),
                     lambda e: e.update(mutations_approved=1),
                     lambda e: e.update(execution="sandbox"),
                     lambda e: e.update(profile_sha256="f" * 64),
                     lambda e: e["baseline"].update(commit="f" * 40),
                     lambda e: e.update(checks={}),
                     lambda e: e["checks"].update(extra={"outcome": "passed", "evidence_ref": "extra"}),
                     lambda e: e["checks"]["test"].update(outcome="failed"),
                     lambda e: e["checks"]["test"].pop("evidence_ref"),
                     lambda e: e.update(secret="W1_SECRET_CANARY")]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                evidence = deepcopy(self.evidence)
                mutation(evidence)
                error = self.rejected(lambda: self.authorize(evidence=evidence))
                self.assertNotIn("W1_SECRET_CANARY", str(error))
                self.assertEqual(self.store.read()["features"], {})

    def test_approved_narrow_exception_is_retained_as_exception_not_pass(self):
        evidence = deepcopy(self.evidence)
        evidence["checks"]["test"] = {"outcome": "exception", "evidence_ref": "baseline-failure",
                                       "failure_ref": "old-failure", "scope_ref": "unrelated-scope",
                                       "approval_ref": "human-exception"}
        for key in ("failure_ref", "scope_ref", "approval_ref"):
            invalid = deepcopy(evidence)
            del invalid["checks"]["test"][key]
            self.rejected(lambda: self.authorize(evidence=invalid))
        self.authorize(evidence=evidence)
        feature = self.store.read()["features"]["project/feature"]
        self.assertEqual(feature["fixture_evidence"], evidence)
        altered = deepcopy(evidence)
        altered["checks"]["test"]["approval_ref"] = "different-approval"
        self.rejected(lambda: self.authorize(evidence=altered), "identity_conflict")

    def test_reviewed_api_and_configuration_must_match_without_loading_them(self):
        for path in (self.api, self.configuration):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"\nW1_SECRET_CANARY\n")
                    error = self.rejected(self.authorize)
                    self.assertNotIn("W1_SECRET_CANARY", str(error))
                    self.assertEqual(self.store.read()["features"], {})
                finally:
                    path.write_bytes(original)

    def test_authorization_freezes_one_link_free_bundle_outside_project(self):
        self.authorize()
        matches = list(self.store.root.rglob("agents/orchestrator.md"))
        self.assertEqual(len(matches), 1)
        snapshot = matches[0].parent.parent
        self.assertFalse(snapshot.is_relative_to(self.root))
        self.assertEqual({p.relative_to(snapshot).as_posix(): digest(p.read_bytes())
                          for p in snapshot.rglob("*") if p.is_file()},
                         {entry["path"]: entry["sha256"] for entry in self.inventory})
        self.assertFalse(any(p.is_symlink() for p in snapshot.rglob("*")))
        self.assertTrue(self.authorize()["existing"])
        self.assertEqual(list(self.store.root.rglob("agents/orchestrator.md")), matches)

    def test_source_bundle_drift_never_changes_existing_feature_snapshot(self):
        authorization = self.approved()
        snapshots = list(self.store.root.rglob("agents/orchestrator.md"))
        self.assertEqual(len(snapshots), 1)
        frozen = snapshots[0].read_bytes()
        (self.bundle / "agents/orchestrator.md").write_bytes(b"# Future feature only\n")
        self.rejected(self.authorize)
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            # Execution consumes the feature's frozen bundle, not mutable installation bytes.
            run = self.claim(session, authorization)["run"]
            self.assertEqual(run["bundle_sha256"], self.bundle_sha256)
        self.assertEqual(snapshots[0].read_bytes(), frozen)

    def test_frozen_bundle_tampering_or_omission_cannot_claim(self):
        authorization = self.approved()
        matches = list(self.store.root.rglob("agents/orchestrator.md"))
        self.assertEqual(len(matches), 1)
        path = matches[0]
        original = path.read_bytes()
        original_mode = path.stat().st_mode & 0o777

        def replace_with_link():
            path.unlink()
            path.symlink_to(self.bundle / "agents/orchestrator.md")

        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            for mutation in (lambda: path.write_bytes(b"# Tampered\n"), path.unlink,
                             replace_with_link):
                with self.subTest(mutation=mutation):
                    try:
                        # Frozen modes are integrity aids, not containment of the same user.
                        path.chmod(0o600)
                        mutation()
                        self.rejected(lambda: self.claim(session, authorization))
                        self.assertEqual(self.store.read()["runs"], {})
                    finally:
                        if path.exists() or path.is_symlink():
                            path.unlink()
                        path.write_bytes(original)
                        path.chmod(original_mode)
            extra = path.parent / "unapproved.md"
            try:
                extra.write_bytes(b"# Added after authorization\n")
                self.rejected(lambda: self.claim(session, authorization))
                self.assertEqual(self.store.read()["runs"], {})
            finally:
                extra.unlink()

    def test_incomplete_bundle_and_declared_digest_mismatch_are_not_authorizations(self):
        path = self.bundle / "provenance.md"
        original = path.read_bytes()
        path.unlink()
        self.rejected(self.authorize)
        self.assertEqual(self.store.read()["features"], {})
        path.write_bytes(original)
        self.manifest["bundle_sha256"] = "f" * 64
        self.save_manifest()
        self.rejected(self.authorize)
        self.assertEqual(self.store.read()["features"], {})

    def test_missing_commit_or_feature_ref_never_establishes_verified_head(self):
        original = deepcopy(self.manifest)
        self.manifest["baseline"]["commit"] = "f" * 40
        self.save_manifest()
        self.evidence = self.fixture_evidence()
        self.rejected(self.authorize)
        self.manifest = original
        self.save_manifest()
        self.evidence = self.fixture_evidence()
        self.git("update-ref", "-d", self.manifest["baseline"]["branch"])
        self.rejected(self.authorize)
        self.assertEqual(self.store.read()["features"], {})

    def new_commit(self):
        # Only disposable Git commits, with all hooks explicitly disabled.
        self.write_at(self.root / "next.txt", b"Unverified fixture change\n")
        self.git("add", "next.txt")
        self.git("-c", "user.name=W1 Fixture", "-c", "user.email=w1@example.invalid",
                 "commit", "-m", "Unverified disposable fixture change")
        return self.git("rev-parse", "HEAD").strip()

    def test_moved_ref_is_held_not_adopted_by_dispatch_claim_or_status(self):
        authorization = self.approved()
        next_commit = self.new_commit()
        self.git("update-ref", self.manifest["baseline"]["branch"], next_commit)
        self.rejected(lambda: self.dispatch(authorization, "03", "dispatch-other"))
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.rejected(lambda: self.claim(session, authorization))
        feature = self.store.read()["features"]["project/feature"]
        self.assertEqual(feature["verified_head"], self.manifest["baseline"])
        self.assertEqual(self.store.read()["runs"], {})
        status = self.launcher.status("project", "feature")
        self.assertEqual(status["verified_head"], self.manifest["baseline"])
        self.assertFalse(status["slices"]["01"]["eligible"])
        self.assertIn("hold", json.dumps(status).lower())

    def test_packed_feature_ref_is_accepted_without_source_git_configuration(self):
        self.git("pack-refs", "--all")
        self.assertFalse((self.root / ".git" / self.manifest["baseline"]["branch"]).exists())
        authorization = self.approved()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.assertEqual(self.claim(session, authorization)["run"]["baseline"], self.manifest["baseline"])

    def test_git_hooks_config_includes_fsmonitor_and_replacements_are_not_executed(self):
        marker = self.base / "git-or-command-executed"
        script = self.base / "canary.sh"
        script.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 97\n")
        script.chmod(0o700)
        hooks = self.base / "hooks"
        hooks.mkdir()
        for name in ("reference-transaction", "post-checkout", "pre-commit"):
            shutil.copyfile(script, hooks / name)
            (hooks / name).chmod(0o700)
        config = self.root / ".git/config"
        config.write_text(config.read_text() +
                          f'\n[core]\n hooksPath = {hooks}\n fsmonitor = {script}\n'
                          f'[include]\n path = {self.base / "invalid-include"}\n')
        (self.base / "invalid-include").write_text("not valid git config\n")
        self.write_at(self.root / f".git/refs/replace/{self.commit}", b"f" * 40 + b"\n")
        self.profile["commands"]["setup"] = [{"argv": [str(script)], "timeout_seconds": 30}]
        self.profile["commands"]["checks"]["test"]["argv"] = [str(script)]
        self.save_profile()
        authorization = self.approved()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.claim(session, authorization)
        self.assertFalse(marker.exists(), "W1 may inspect objects, never execute source Git config or project commands")

    def test_git_alternates_and_symlinked_metadata_are_not_independent_baselines(self):
        alternates = self.root / ".git/objects/info/alternates"
        alternates.write_text(str(self.base / "other-objects") + "\n")
        self.rejected(self.authorize)
        alternates.unlink()
        objects = self.root / ".git/objects"
        moved = self.base / "redirected-objects"
        objects.rename(moved)
        objects.symlink_to(moved, target_is_directory=True)
        self.rejected(self.authorize)
        self.assertEqual(self.store.read()["features"], {})

    def test_selected_dispatch_cannot_expand_scope_or_be_rebound(self):
        authorization = self.approved()
        self.rejected(lambda: self.dispatch(authorization, "03"), "identity_conflict")
        self.rejected(lambda: self.dispatch("f" * 64, "01", "dispatch-2"))
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.rejected(lambda: self.claim(session, authorization, slice_id="03"))
            self.rejected(lambda: self.claim(session, authorization, dispatch_id="missing"))
            self.rejected(lambda: self.claim(session, "f" * 64))
        self.assertEqual(self.store.read()["runs"], {})

    def test_blocked_selected_consumer_does_not_claim_ready_alternative(self):
        authorization = self.authorize()["authorization_id"]
        # Administration may reject non-ready scope early, or persist it for claim-time checking.
        try:
            self.dispatch(authorization, "02", "consumer")
        except RoutineError:
            pass
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.rejected(lambda: self.claim(session, authorization, "02", "consumer-run", "consumer"))
        self.assertEqual(self.store.read()["runs"], {})
        status = self.launcher.status("project", "feature")
        self.assertEqual(status["slices"]["02"]["waiting_for"], ["01"])
        for slice_id in ("01", "03"):
            self.assertIsNone(status["slices"][slice_id]["run_id"])

    def test_owner_claim_is_not_verified_dependency_integration(self):
        authorization = self.approved()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.claim(session, authorization)
            try:
                self.dispatch(authorization, "02", "consumer")
            except RoutineError:
                pass
            self.rejected(lambda: self.claim(session, authorization, "02", "consumer-run", "consumer"))
        self.assertEqual(set(self.store.read()["runs"]), {"project/run-1"})

    def test_concurrent_duplicates_and_competing_ids_keep_one_exclusive_claim(self):
        authorization = self.approved()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: self.claim(session, authorization), range(24)))
            self.assertEqual(sum(not r["existing"] for r in results), 1)
            self.assertTrue(all(r["run"] == results[0]["run"] for r in results))
            self.rejected(lambda: self.claim(session, authorization, run_id="other-run"), "slice_claimed")
        self.assertEqual(set(self.store.read()["runs"]), {"project/run-1"})

    def test_request_identity_includes_dispatch_baseline_and_exact_branch(self):
        authorization = self.approved()
        self.dispatch(authorization, "01", "dispatch-2")
        self.dispatch(authorization, "03", "dispatch-3")
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.claim(session, authorization)
            before = self.store.read()
            self.rejected(lambda: self.claim(session, authorization, dispatch_id="dispatch-2"))
            self.rejected(lambda: self.claim(session, authorization, "03", dispatch_id="dispatch-3"))
            for changed in ({**self.manifest["baseline"], "commit": "f" * 40},
                            {**self.manifest["baseline"], "branch": "refs/heads/main"},
                            {**self.manifest["baseline"], "extra": "not approved"}):
                self.rejected(lambda: self.claim(session, authorization, baseline=changed))
            self.assertEqual(before, self.store.read())

    def test_identical_claim_after_clean_restart_reuses_durable_run(self):
        authorization = self.approved()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            first = self.claim(session, authorization)
        restarted = Launcher(Store(self.store.root))
        with restarted.coordinator("project", "feature", "coordinator") as session:
            second = self.claim(session, authorization)
        self.assertTrue(second["existing"])
        self.assertEqual(first["run"], second["run"])

    def test_exclusive_lease_and_closed_session_rejection(self):
        authorization = self.approved()
        with self.launcher.coordinator("project", "feature", "first") as session:
            with self.assertRaises(RoutineError) as caught:
                with self.launcher.coordinator("project", "feature", "second"):
                    self.fail("Second feature Coordinator admitted")
            self.assertEqual(caught.exception.code, "coordinator_busy")
        self.rejected(lambda: self.claim(session, authorization), "inactive_coordinator")
        self.assertEqual(self.store.read()["runs"], {})

    def test_invalid_typed_ids_and_baseline_fail_without_claim(self):
        authorization = self.approved()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            for value in (None, {}, [], True, "../01", "", "x" * 65):
                with self.subTest(value=value):
                    self.rejected(lambda: self.claim(session, authorization, slice_id=value))
                    self.rejected(lambda: self.claim(session, authorization, dispatch_id=value))
            for baseline in (None, [], {}, "HEAD", {"commit": self.commit}):
                self.rejected(lambda: session.claim_local("01", "run-1", authorization, "dispatch-1", baseline))
        self.assertEqual(self.store.read()["runs"], {})

    def historical_fixture(self):
        """Build genuine historical records without importing historical test helpers."""
        local_profile = (self.root / ".opencode/routine/project.json").read_bytes()
        historical_profile = {
            "version": 1,
            "commands": {"setup": [], "checks": {"test": {"argv": ["true"], "timeout_seconds": 30}}},
            "services": [], "mounts": [], "network": {"allowed_domains": []},
            "credential_refs": [], "providers": [],
            "resources": {"cpus": 1, "memory_mb": 512, "pids": 64, "disk_mb": 1024,
                          "log_mb": 16, "command_seconds": 60},
            "budgets": deepcopy(self.profile["budgets"]), "qa": {"kind": "none", "start": None}}
        data = canonical(historical_profile)
        self.write_at(self.root / ".opencode/routine/project.json", data)
        historical = deepcopy(self.manifest)
        historical.update(version=1, feature_id="historical", profile_sha256=digest(data), bundle_sha256="b" * 64)
        del historical["execution"]
        self.save_manifest(historical)
        try:
            authorization = self.launcher.authorize("project", "historical", self.root)["authorization_id"]
            with self.launcher.coordinator("project", "historical", "old-coordinator") as session:
                session.claim("01", "old-run", authorization)
        finally:
            self.write_at(self.root / ".opencode/routine/project.json", local_profile)
        with self.store.lock("ledger.lock"):
            ledger = self.store.read()
            ledger["runs"]["project/old-run"]["inspection"] = {"status": "historical", "evidence_ref": "old-inspection"}
            ledger["runs"]["project/old-run"]["environment"] = {"state": "retained", "identity": "old-environment"}
            ledger["inspections"] = {"old-inspection": {"retained": True}}
            ledger["environments"] = {"old-environment": {"retained": True}}
            ledger["qa"] = {"human-preview": {"owner": "user", "state": "running"}}
            ledger["unrelated"] = {"nested": [1, {"keep": "exactly"}]}
            self.store.write(ledger)
        return authorization

    def test_historical_records_and_unrelated_ledger_sections_are_byte_equivalent(self):
        self.historical_fixture()
        before = self.store.read()
        authorization = self.approved()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.claim(session, authorization)
            self.launcher.status("project", "feature")
        after = self.store.read()
        self.assertEqual(canonical(before["features"]["project/historical"]),
                         canonical(after["features"]["project/historical"]))
        self.assertEqual(canonical(before["runs"]["project/old-run"]),
                         canonical(after["runs"]["project/old-run"]))
        for section in ("inspections", "environments", "qa", "unrelated"):
            self.assertEqual(canonical(before[section]), canonical(after[section]))
        self.assertNotIn("execution", after["features"]["project/historical"])
        self.assertNotIn("execution", after["runs"]["project/old-run"])

    def test_local_and_historical_authorizations_and_run_ids_cannot_cross_use(self):
        historical_authorization = self.historical_fixture()
        authorization = self.approved()
        self.rejected(lambda: self.launcher.authorize_local_dispatch(
            "project", "historical", "03", "local-dispatch", historical_authorization))
        with self.launcher.coordinator("project", "historical", "old-coordinator") as session:
            self.rejected(lambda: session.claim_local("03", "wrong-run", historical_authorization,
                                                     "local-dispatch", self.manifest["baseline"]))
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.rejected(lambda: session.claim("01", "wrong-run", authorization))
            self.rejected(lambda: self.claim(session, historical_authorization))
            self.rejected(lambda: self.claim(session, authorization, run_id="old-run"))
        self.assertEqual(set(self.store.read()["runs"]), {"project/old-run"})

    def test_mixed_manifest_profile_versions_and_historical_admin_route_reject_local(self):
        self.rejected(lambda: self.launcher.authorize("project", "feature", self.root))
        original = deepcopy(self.manifest)
        for mutation in (lambda m: m.update(version=1),
                         lambda m: m.update(execution="sandbox"),
                         lambda m: m.pop("execution")):
            with self.subTest(mutation=mutation):
                self.manifest = deepcopy(original)
                mutation(self.manifest)
                self.save_manifest()
                self.rejected(self.authorize)
        self.assertEqual(self.store.read()["features"], {})

    def test_sandbox_operations_reject_local_before_any_adapter_effect(self):
        authorization = self.approved()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            self.claim(session, authorization)
            targets = [("routine.sandbox.Sandbox.launch", session.baseline),
                       ("routine.proxy.ProxyCheck.launch", session.proxy_check),
                       ("routine.environment.Environment.prepare", session.environment_plan),
                       ("routine.environment.Environment.launch", session.environment_check)]
            for target, operation in targets:
                with self.subTest(target=target), patch(target) as adapter:
                    adapter.side_effect = AssertionError("Sandbox adapter invoked for local authorization")
                    self.rejected(lambda: operation("run-1"))
                    adapter.assert_not_called()

    def test_project_identity_cannot_rebind_and_state_cannot_live_in_project(self):
        self.authorize()
        original = self.root
        other = self.base / "other-project"
        shutil.copytree(original, other)
        try:
            self.root = other
            self.rejected(self.authorize, "identity_conflict")
        finally:
            self.root = original
        unsafe = Launcher(Store(self.root / "unsafe-state"))
        self.rejected(lambda: self.authorize(launcher=unsafe), "unsafe_state")
        self.assertEqual(unsafe.store.read()["features"], {})

    def test_snapshot_copy_failure_retains_diagnostics_without_publishing_feature(self):
        partials = []

        def interrupted_copy(root, destination, expected_sha256, **limits):
            destination = Path(destination)
            destination.mkdir(parents=True, exist_ok=False)
            self.write_at(destination / "agents/orchestrator.md", b"Partial copy\n")
            partials.append(destination)
            raise OSError("Injected disposable copy interruption")

        with patch("routine.local_bundle.snapshot_bundle", side_effect=interrupted_copy):
            with self.assertRaises((RoutineError, OSError)):
                self.authorize()
        self.assertEqual(self.store.read()["features"], {})
        self.assertEqual(len(partials), 1)
        self.assertTrue((partials[0] / "agents/orchestrator.md").exists())

    def child(self, script, *args, input=None):
        return subprocess.run([sys.executable, "-c", script, *map(str, args)],
                              env=self.env(), input=input, capture_output=True, text=True, timeout=15)

    def test_atomic_authorization_is_old_or_new_complete_at_each_checkpoint(self):
        for stage in ("before_replace", "after_replace", "after_directory_sync"):
            with self.subTest(stage=stage):
                state = self.base / f"authorize-{stage}"
                launcher = Launcher(Store(state))
                evidence_file = self.base / "fixture-evidence.json"
                evidence_file.write_bytes(canonical(self.evidence))
                script = """
import json, os, sys
from routine.launcher import Launcher
from routine.store import Store
store = Store(sys.argv[1])
def checkpoint(stage):
    if stage == sys.argv[2]:
        os._exit(42)
store.checkpoint = checkpoint
Launcher(store).authorize_local('project', 'feature', *sys.argv[3:7],
                               json.loads(open(sys.argv[7]).read()))
"""
                result = self.child(script, state, stage, self.root, self.bundle, self.api,
                                    self.configuration, evidence_file)
                self.assertEqual(result.returncode, 42, result.stdout + result.stderr)
                ledger = launcher.store.read()
                published = stage != "before_replace"
                self.assertEqual("project/feature" in ledger["features"], published)
                self.assertEqual(ledger["runs"], {})
                if published:
                    feature = ledger["features"]["project/feature"]
                    self.assertEqual(feature["execution"], "trusted-local")
                    self.assertEqual(feature["verified_head"], self.manifest["baseline"])
                    self.assertEqual(feature["fixture_evidence"], self.evidence)
                    self.assertEqual(set(feature["slices"]), {"01", "02", "03"})
                    self.assertTrue(launcher.authorize_local(
                        "project", "feature", self.root, self.bundle, self.api,
                        self.configuration, self.evidence)["existing"])

    def test_atomic_dispatch_is_old_or_new_complete_at_each_checkpoint(self):
        for stage in ("before_replace", "after_replace", "after_directory_sync"):
            with self.subTest(stage=stage):
                launcher = Launcher(Store(self.base / f"dispatch-{stage}"))
                authorization = self.authorize(launcher=launcher)["authorization_id"]
                before = launcher.store.read()
                script = """
import os, sys
from routine.launcher import Launcher
from routine.store import Store
store = Store(sys.argv[1])
def checkpoint(stage):
    if stage == sys.argv[2]:
        os._exit(42)
store.checkpoint = checkpoint
Launcher(store).authorize_local_dispatch('project', 'feature', '01', 'dispatch-1', sys.argv[3])
"""
                result = self.child(script, launcher.store.root, stage, authorization)
                self.assertEqual(result.returncode, 42, result.stdout + result.stderr)
                ledger = launcher.store.read()
                dispatches = ledger["features"]["project/feature"]["dispatches"]
                self.assertEqual("dispatch-1" in dispatches, stage != "before_replace")
                self.assertEqual(ledger["runs"], {})
                # Removing just the intended dispatch leaves the entire old ledger unchanged.
                comparison = deepcopy(ledger)
                comparison["features"]["project/feature"]["dispatches"] = before["features"]["project/feature"]["dispatches"]
                self.assertEqual(comparison, before)
                repeated = self.dispatch(authorization, launcher=launcher)
                self.assertEqual(repeated["existing"], stage != "before_replace")

    def test_atomic_claim_and_kernel_release_preserve_deliberate_recovery_hold(self):
        for stage in ("before_replace", "after_replace", "after_directory_sync"):
            with self.subTest(stage=stage):
                launcher = Launcher(Store(self.base / f"claim-{stage}"))
                authorization = self.authorize(launcher=launcher)["authorization_id"]
                self.dispatch(authorization, launcher=launcher)
                lock = launcher.store.root / "ledger.lock"
                inode = lock.stat().st_ino
                script = """
import json, os, sys
from routine.launcher import Launcher
from routine.store import Store
store = Store(sys.argv[1])
launcher = Launcher(store)
with launcher.coordinator('project', 'feature', 'crashed') as session:
    def checkpoint(stage):
        if stage == sys.argv[2]:
            os._exit(42)
    store.checkpoint = checkpoint
    session.claim_local('01', 'run-1', sys.argv[3], 'dispatch-1', json.loads(sys.argv[4]))
"""
                result = self.child(script, launcher.store.root, stage, authorization,
                                    json.dumps(self.manifest["baseline"]))
                self.assertEqual(result.returncode, 42, result.stdout + result.stderr)
                ledger = Store(launcher.store.root).read()
                claimed = stage != "before_replace"
                self.assertEqual("project/run-1" in ledger["runs"], claimed)
                feature = ledger["features"]["project/feature"]
                self.assertEqual(feature["slices"]["01"],
                                 {"state": "claimed" if claimed else "pending",
                                  "run_id": "run-1" if claimed else None})
                self.assertEqual(feature["coordinator"]["id"], "crashed")
                self.assertEqual(lock.stat().st_ino, inode)
                # Acquire the exact lease inode: kernel ownership ended, persisted hold did not.
                lease_names = list(launcher.store.root.glob("coordinator-*.lock"))
                self.assertEqual(len(lease_names), 1)
                with launcher.store.lock(lease_names[0].name, blocking=False):
                    pass
                with self.assertRaises(RoutineError) as caught:
                    with launcher.coordinator("project", "feature", "replacement"):
                        self.fail("Implicit Coordinator crash recovery admitted")
                self.assertEqual(caught.exception.code, "recovery_required")
                status = launcher.status("project", "feature")
                self.assertIn("hold", json.dumps(status).lower())
                self.assertFalse(status["slices"]["03"]["eligible"])
                self.assertEqual(ledger, launcher.store.read(), "Status must not mutate recovery authority")

    def cli(self, *args, input=None):
        return subprocess.run([sys.executable, str(ENTRY), *map(str, args)], env=self.env(),
                              input=input, capture_output=True, text=True, timeout=15)

    def cli_authorize(self):
        evidence_file = self.base / "fixture-evidence.json"
        evidence_file.write_bytes(canonical(self.evidence))
        result = self.cli("authorize-local", "--project", "project", "--feature", "feature",
                          "--root", self.root, "--bundle-root", self.bundle, "--api-input", self.api,
                          "--configuration-input", self.configuration, "--fixture-evidence", evidence_file)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)["authorization_id"]

    def test_cli_local_bundle_identity_is_distinct_from_worker_image_identity(self):
        result = self.cli("local-bundle-id", "--root", self.bundle)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        identity = json.loads(result.stdout)
        self.assertEqual(identity["bundle_sha256"], self.bundle_sha256)
        self.assertEqual(identity["execution"], "trusted-local")
        self.assertEqual(identity["inventory"], self.inventory)

    def test_cli_local_typed_surface_rejects_roots_commands_execution_and_missing_fields(self):
        authorization = self.cli_authorize()
        result = self.cli("authorize-local-dispatch", "--project", "project", "--feature", "feature",
                          "--slice", "01", "--dispatch", "dispatch-1", "--authorization", authorization)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        dispatch = json.loads(result.stdout)
        self.assertEqual(dispatch["dispatch_id"], "dispatch-1")
        request = {"operation": "local-claim", "slice_id": "01", "run_id": "run-1",
                   "authorization_id": authorization, "dispatch_id": "dispatch-1",
                   "baseline": self.manifest["baseline"], "execution": "trusted-local"}
        invalid = [{**request, "root": str(self.root)}, {**request, "command": "touch canary"},
                   {**request, "execution": "sandbox"},
                   {k: v for k, v in request.items() if k != "dispatch_id"},
                   {"operation": "authorize-local", "root": str(self.root)}, ["not an object"]]
        requests = [request, request, {"operation": "status"}, *invalid]
        result = self.cli("coordinate", "--project", "project", "--feature", "feature",
                          "--coordinator", "coordinator",
                          input="".join(json.dumps(r) + "\n" for r in requests))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(responses), len(requests) + 1)
        self.assertEqual(responses[0]["operation"], "coordinator_opened")
        self.assertFalse(responses[1]["existing"])
        self.assertTrue(responses[2]["existing"])
        self.assertEqual(responses[3]["execution"], "trusted-local")
        for response in responses[4:]:
            self.assertEqual(set(response), {"error"})
            self.assertEqual(set(response["error"]), {"code", "message"})
        ledger = Store(self.base / "cli-state/opencode-routine").read()
        self.assertEqual(set(ledger["runs"]), {"project/run-1"})

    def test_cli_process_lease_blocks_another_owner_without_starting_runtime(self):
        self.cli_authorize()
        command = [sys.executable, str(ENTRY), "coordinate", "--project", "project",
                   "--feature", "feature", "--coordinator", "first"]
        owner = subprocess.Popen(command, env=self.env(), stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(json.loads(owner.stdout.readline())["operation"], "coordinator_opened")
            other = self.cli("coordinate", "--project", "project", "--feature", "feature",
                             "--coordinator", "second", input="")
            self.assertEqual(other.returncode, 1)
            self.assertEqual(json.loads(other.stdout)["error"]["code"], "coordinator_busy")
        finally:
            if owner.poll() is None:
                owner.communicate(timeout=10)
            else:
                owner.communicate()
        self.assertEqual(owner.returncode, 0)


if __name__ == "__main__":
    unittest.main()
