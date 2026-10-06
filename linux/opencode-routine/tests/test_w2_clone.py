"""W2 clone/handoff contract tests; isolated trusted Git fixtures, not runtime proof."""
from copy import deepcopy
import errno
import os
from pathlib import Path
import subprocess
import stat
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".local/lib/opencode-routine"))

from routine.contracts import RoutineError, canonical, digest, parse_json
from routine.local_bundle import describe_bundle, snapshot_bundle


class CloneTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="w2-clone-", dir="/tmp/opencode")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self.git("init", "--template=", str(self.root))
        (self.root / "app.txt").write_text("approved baseline\n")
        self.git("-C", str(self.root), "add", "app.txt")
        self.git("-C", str(self.root), "-c", "user.name=Fixture", "-c",
                 "user.email=fixture@example.invalid", "commit", "-m", "Fixture baseline")
        self.commit = self.git("-C", str(self.root), "rev-parse", "HEAD").decode().strip()
        self.baseline = {"commit": self.commit, "branch": "refs/heads/features/fixture"}
        self.git("-C", str(self.root), "update-ref", self.baseline["branch"], self.commit)
        bundle = self.base / "bundle-source"
        (bundle / "agents").mkdir(parents=True)
        (bundle / "skills/tdd/resources").mkdir(parents=True)
        (bundle / "agents/builder.md").write_text("Fixture Builder\n")
        (bundle / "skills/tdd/SKILL.md").write_text("Fixture TDD\n")
        (bundle / "skills/tdd/resources/example.txt").write_text("Full resource\n")
        (bundle / "provenance.md").write_text("Trusted fixture only\n")
        description = describe_bundle(bundle, max_bytes=100000, timeout=5)
        frozen = self.base / "frozen-bundle"
        snapshot_bundle(bundle, frozen, description["sha256"], max_bytes=100000, timeout=5)
        spec = "# Full spec\n<!-- criterion: C1 -->\nExact requirement.\n"
        ticket = "# Slice\nC1 mapping and implementation context.\n"
        other = "# Other slice\nThe entire planning package is retained.\n"
        profile = {"version": 4, "execution": "trusted-local", "commands": {
            "setup": [], "checks": {"unit": {"argv": ["true"], "timeout_seconds": 5}}},
            "command_limits": {"command_seconds": 10, "input_bytes": 1000000, "output_bytes": 1000000},
            "budgets": {"slice_seconds": 60, "inactivity_seconds": 30, "integration_seconds": 60, "repairs": 2},
            "concurrency": {"workers_per_feature": 3}, "credential_refs": [],
            "runtime": {"opencode_version": "2.0.22", "api_sha256": "a" * 64,
                        "configuration_sha256": "b" * 64, "connection_ref": "fixture"},
            "services": [], "qa": {"kind": "none", "start": None}}
        manifest = {"version": 2, "execution": "trusted-local", "feature_id": "fixture",
            "spec": {"path": "docs/spec.md", "sha256": digest(spec.encode()), "criteria": ["C1"]},
            "tickets": [{"slice_id": "slice", "path": "tickets/slice.md", "sha256": digest(ticket.encode()),
                         "criteria": ["C1"], "dependencies": []},
                        {"slice_id": "other", "path": "tickets/other.md", "sha256": digest(other.encode()),
                         "criteria": ["C1"], "dependencies": ["slice"]}],
            "profile_sha256": digest(canonical(profile)), "bundle_sha256": description["sha256"],
            "baseline": deepcopy(self.baseline)}
        snapshots = {"docs/spec.md": spec, "tickets/slice.md": ticket, "tickets/other.md": other,
                     ".opencode/routine/project.json": canonical(profile).decode(),
                     ".opencode/routine/features/fixture/approval.json": canonical(manifest).decode()}
        for name, text in snapshots.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode())
        self.feature = {"schema_version": 1, "execution": "trusted-local", "project_root": str(self.root),
                        "authorization_id": "c" * 64, "verified_head": deepcopy(self.baseline),
                        "package": {"manifest": manifest, "profile": profile, "snapshots": snapshots},
                        "bundle_snapshot": {"path": str(frozen), **description}}
        self.run = {"schema_version": 1, "execution": "trusted-local", "state": "claimed",
                    "request": {"execution": "trusted-local", "project_id": "project", "feature_id": "fixture",
                                "slice_id": "slice", "run_id": "run", "authorization_id": "c" * 64,
                                "coordinator_id": "coord", "dispatch_id": "dispatch",
                                "dispatch_authorization_id": "d" * 64, "baseline": deepcopy(self.baseline)},
                    "baseline": deepcopy(self.baseline), "bundle_snapshot": deepcopy(self.feature["bundle_snapshot"]),
                    "bundle_sha256": description["sha256"], "profile_sha256": manifest["profile_sha256"],
                    "spec_sha256": manifest["spec"]["sha256"], "ticket_sha256": manifest["tickets"][0]["sha256"],
                    "criteria": ["C1"], "budgets": deepcopy(profile["budgets"]),
                    "command_limits": deepcopy(profile["command_limits"]), "credential_refs": []}
        self.destination = self.base / "artifacts"
        self.events = []

    def git(self, *args):
        return subprocess.run(["/usr/bin/git", *args], check=True, capture_output=True,
                              env={"PATH": "/usr/bin:/bin", "HOME": str(self.base),
                                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}).stdout

    def prepare(self, **kwargs):
        from routine.local_run import prepare_clone
        return prepare_clone(self.feature, self.run, self.destination, timeout=kwargs.get("timeout", 10),
                             max_bytes=kwargs.get("max_bytes", 1000000),
                             checkpoint=kwargs.get("checkpoint", lambda name, details: self.events.append((name, details))))

    def verify(self, prepared, **kwargs):
        from routine.local_run import verify_prepared
        return verify_prepared(prepared, self.run, timeout=kwargs.get("timeout", 10),
                               max_bytes=kwargs.get("max_bytes", 1000000))

    def test_exact_independent_clone_and_full_readable_handoff(self):
        feature, run = deepcopy(self.feature), deepcopy(self.run)
        prepared = self.prepare()
        self.assertEqual(set(prepared), {"artifact", "checkout", "branch", "commit", "git_dir", "bundle_sha256", "handoff"})
        self.assertEqual(prepared["branch"], "routine/fixture/slice/run")
        self.assertEqual(prepared["commit"], self.commit)
        checkout = Path(prepared["checkout"])
        self.assertEqual(self.git("-C", str(checkout), "rev-parse", "HEAD").decode().strip(), self.commit)
        self.assertEqual((checkout / "app.txt").read_text(), "approved baseline\n")
        self.assertTrue((checkout / ".git").is_dir())
        self.assertFalse((checkout / ".git/objects/info/alternates").exists())
        self.assertEqual(set(prepared["handoff"]), {"path", "sha256", "inventory"})
        handoff = Path(prepared["handoff"]["path"])
        for name, text in self.feature["package"]["snapshots"].items():
            self.assertEqual((handoff / "planning" / name).read_bytes(), text.encode())
        self.assertEqual((handoff / "bundle/skills/tdd/resources/example.txt").read_text(), "Full resource\n")
        context = parse_json((handoff / "context.json").read_bytes())
        self.assertEqual(context["criteria"], ["C1"])
        self.assertEqual(context["request"], self.run["request"])
        self.assertIn("planning/docs/spec.md", (handoff / "README.md").read_text())
        inventory = prepared["handoff"]["inventory"]
        self.assertEqual(inventory, sorted(inventory, key=lambda entry: entry["path"]))
        self.assertEqual(digest(canonical(inventory)), prepared["handoff"]["sha256"])
        self.assertEqual(self.verify(prepared), prepared)
        self.assertEqual((self.feature, self.run), (feature, run))
        source_inodes = {(p.stat().st_dev, p.stat().st_ino) for p in (self.root / ".git").rglob("*") if p.is_file()}
        for path in (checkout / ".git").rglob("*"):
            if path.is_file():
                self.assertEqual(path.stat().st_nlink, 1)
                self.assertNotIn((path.stat().st_dev, path.stat().st_ino), source_inodes)
        for effect in ("artifact", "export", "clone", "handoff"):
            phases = [details["phase"] for name, details in self.events if name == effect]
            self.assertEqual(phases, ["intent", "observed"])

    def test_two_runs_have_distinct_git_state(self):
        first = self.prepare()
        self.destination = self.base / "second-artifacts"
        self.run["request"]["run_id"] = "second"
        second = self.prepare()
        self.assertNotEqual(first["git_dir"], second["git_dir"])
        self.assertNotEqual(first["branch"], second["branch"])
        (Path(first["git_dir"]) / "refs/heads/private").write_text(self.commit + "\n")
        self.assertFalse((Path(second["git_dir"]) / "refs/heads/private").exists())

    def test_source_and_ambient_git_configuration_never_execute(self):
        canary = self.base / "executed"
        hook = self.base / "hook"
        hook.write_text(f"#!/bin/sh\ntouch {canary}\n")
        hook.chmod(0o755)
        (self.root / ".git/config").write_text(f"[core]\nfsmonitor = {hook}\nhooksPath = {self.base}\n[include]\npath = /missing\n")
        (self.base / "post-checkout").write_bytes(hook.read_bytes())
        (self.base / "post-checkout").chmod(0o755)
        with patch.dict(os.environ, {"GIT_CONFIG_COUNT": "invalid", "GIT_TEMPLATE_DIR": str(self.base),
                                     "GIT_DIR": str(self.root / ".git")}):
            prepared = self.prepare()
            self.verify(prepared)
        self.assertFalse(canary.exists())
        self.assertFalse((Path(prepared["git_dir"]) / "hooks").exists())

    def test_no_existing_destination_is_adopted_or_overwritten(self):
        for kind in ("directory", "file", "symlink", "dangling"):
            with self.subTest(kind=kind):
                destination = self.base / kind
                if kind == "directory":
                    destination.mkdir()
                    (destination / "sentinel").write_text("keep")
                elif kind == "file":
                    destination.write_text("keep")
                else:
                    destination.symlink_to(self.root if kind == "symlink" else self.base / "missing")
                self.destination = destination
                with self.assertRaises(RoutineError) as caught:
                    self.prepare()
                self.assertEqual(caught.exception.code, "artifact_exists")
                self.assertTrue(destination.exists() or destination.is_symlink())

    def test_repeat_success_is_not_adopted(self):
        prepared = self.prepare()
        with self.assertRaises(RoutineError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.code, "artifact_exists")
        self.verify(prepared)

    def test_checkpoint_stop_retains_partial_artifacts(self):
        def stop(name, details):
            self.events.append((name, details))
            if name == "export" and details["phase"] == "observed":
                raise RoutineError("stopping", "Stopped by owner")
        with self.assertRaises(RoutineError):
            self.prepare(checkpoint=stop)
        self.assertTrue((self.destination / "source.bundle").is_file())
        self.assertFalse((self.destination / "checkout").exists())
        with self.assertRaises(RoutineError):
            self.prepare()

    def test_changed_planning_or_frozen_bundle_is_rejected(self):
        (self.root / "tickets/other.md").write_text("drift")
        with self.assertRaises(RoutineError):
            self.prepare()
        (self.root / "tickets/other.md").write_text(self.feature["package"]["snapshots"]["tickets/other.md"])
        frozen = Path(self.run["bundle_snapshot"]["path"]) / "agents/builder.md"
        frozen.chmod(0o600)
        frozen.write_text("drift")
        with self.assertRaises(RoutineError):
            self.prepare()

    def test_baseline_move_and_source_alternates_rejected(self):
        ref = self.root / ".git" / self.baseline["branch"]
        ref.write_text("f" * 40 + "\n")
        with self.assertRaises(RoutineError):
            self.prepare()
        ref.write_text(self.commit + "\n")
        (self.root / ".git/objects/info/alternates").write_text("/missing\n")
        with self.assertRaises(RoutineError):
            self.prepare()

    def test_combined_bound_counts_export_planning_and_bundle(self):
        prepared = self.prepare()
        total = (self.destination / "source.bundle").stat().st_size + sum(
            (Path(prepared["handoff"]["path"]) / entry["path"]).stat().st_size
            for entry in prepared["handoff"]["inventory"])
        self.verify(prepared, max_bytes=total)
        with self.assertRaises(RoutineError):
            self.verify(prepared, max_bytes=total - 1)
        self.destination = self.base / "bounded"
        with self.assertRaises(RoutineError):
            self.prepare(max_bytes=total - 1)
        self.assertTrue(self.destination.exists())

    def test_overall_deadline_rejects_late_checkpoint(self):
        monotonic, offset = time.monotonic, [0]
        def late(name, details):
            if name == "artifact" and details["phase"] == "observed":
                offset[0] = 20
        with patch("routine.local_run.time.monotonic", side_effect=lambda: monotonic() + offset[0]):
            with self.assertRaises(RoutineError) as caught:
                self.prepare(timeout=10, checkpoint=late)
        self.assertEqual(caught.exception.code, "command_timeout")
        self.assertTrue(self.destination.exists())

    def test_verification_rejects_handoff_membership_and_bytes_drift(self):
        prepared = self.prepare()
        handoff = Path(prepared["handoff"]["path"])
        path = handoff / "planning/docs/spec.md"
        original = path.read_bytes()
        path.chmod(0o600)
        path.write_bytes(b"drift")
        with self.assertRaises(RoutineError):
            self.verify(prepared)
        path.write_bytes(original)
        extra = handoff / "extra"
        extra.write_text("extra")
        with self.assertRaises(RoutineError):
            self.verify(prepared)
        extra.unlink()
        path.unlink()
        with self.assertRaises(RoutineError):
            self.verify(prepared)

    def test_verification_rejects_links_worktrees_and_hardlinks(self):
        prepared = self.prepare()
        git_dir = Path(prepared["git_dir"])
        alternate = git_dir / "objects/info/alternates"
        alternate.write_text(str(self.root / ".git/objects") + "\n")
        with self.assertRaises(RoutineError):
            self.verify(prepared)
        alternate.unlink()
        (git_dir / "commondir").write_text(str(self.root / ".git"))
        with self.assertRaises(RoutineError):
            self.verify(prepared)
        (git_dir / "commondir").unlink()
        path = git_dir / "config"
        linked = self.base / "hardlinked-config"
        os.link(path, linked)
        with self.assertRaises(RoutineError):
            self.verify(prepared)
        linked.unlink()
        handoff_file = Path(prepared["handoff"]["path"]) / "bundle/agents/builder.md"
        handoff_file.unlink()
        handoff_file.symlink_to(Path(self.run["bundle_snapshot"]["path"]) / "agents/builder.md")
        with self.assertRaises(RoutineError):
            self.verify(prepared)

    def test_verification_rejects_branch_commit_and_run_drift(self):
        prepared = self.prepare()
        head = Path(prepared["git_dir"]) / "HEAD"
        original = head.read_bytes()
        head.write_text(self.commit + "\n")
        with self.assertRaises(RoutineError):
            self.verify(prepared)
        head.write_bytes(original)
        self.run["criteria"] = ["other"]
        with self.assertRaises(RoutineError):
            self.verify(prepared)

    def test_export_tamper_is_rejected(self):
        prepared = self.prepare()
        (self.destination / "source.bundle").write_bytes(b"changed")
        with self.assertRaises(RoutineError):
            self.verify(prepared)

    def test_unsafe_parent_and_destination_inside_project_rejected(self):
        linked = self.base / "linked-parent"
        linked.symlink_to(self.base, target_is_directory=True)
        self.destination = linked / "artifact"
        with self.assertRaises(RoutineError):
            self.prepare()
        self.destination = self.root / "artifact"
        with self.assertRaises(RoutineError):
            self.prepare()

    def test_invalid_limits_and_execution_kind_fail_closed(self):
        for bound in (0, -1, True, float("inf"), float("nan")):
            with self.subTest(bound=bound), self.assertRaises(RoutineError):
                self.prepare(timeout=bound)
        for bound in (0, -1, True, 1.5):
            with self.subTest(bound=bound), self.assertRaises(RoutineError):
                self.prepare(max_bytes=bound)
        self.run["execution"] = "sandbox"
        with self.assertRaises(RoutineError):
            self.prepare()

    def test_malformed_inputs_use_fixed_routine_diagnostics(self):
        approval = ".opencode/routine/features/fixture/approval.json"
        self.feature["package"]["snapshots"][approval] = '{"SECRET_CANARY":1,"SECRET_CANARY":2}'
        with self.assertRaises(RoutineError) as caught:
            self.prepare()
        self.assertNotIn("SECRET_CANARY", str(caught.exception))
        self.run = {}
        with self.assertRaises(RoutineError):
            self.prepare()

    def test_small_bound_does_not_write_unbounded_generated_handoff(self):
        prepared = self.prepare()
        limit = (self.destination / "source.bundle").stat().st_size + sum(
            (Path(prepared["handoff"]["path"]) / entry["path"]).stat().st_size
            for entry in prepared["handoff"]["inventory"]) - 100
        self.destination = self.base / "too-small"
        with self.assertRaises(RoutineError):
            self.prepare(max_bytes=limit)
        size = (self.destination / "source.bundle").stat().st_size + sum(
            path.stat().st_size for path in (self.destination / "handoff").rglob("*") if path.is_file())
        self.assertLessEqual(size, limit)

    def test_source_uncommitted_content_is_not_adopted(self):
        (self.root / "app.txt").write_text("uncommitted change")
        prepared = self.prepare()
        self.assertEqual((Path(prepared["checkout"]) / "app.txt").read_text(), "approved baseline\n")
        self.assertEqual((self.root / "app.txt").read_text(), "uncommitted change")

    def test_packed_source_ref_is_supported(self):
        self.git("-C", str(self.root), "pack-refs", "--all")
        self.verify(self.prepare())

    def test_noncommit_object_is_not_peeled_or_adopted(self):
        self.git("-C", str(self.root), "-c", "user.name=Fixture", "-c",
                 "user.email=fixture@example.invalid", "tag", "-a", "fixture-tag", "-m", "Fixture", self.commit)
        tag = self.git("-C", str(self.root), "rev-parse", "fixture-tag").decode().strip()
        for baseline in (self.feature["verified_head"], self.run["baseline"], self.run["request"]["baseline"]):
            baseline["commit"] = tag
        (self.root / ".git" / self.baseline["branch"]).write_text(tag + "\n")
        with self.assertRaises(RoutineError):
            self.prepare()

    def test_late_final_fence_is_not_a_success(self):
        monotonic, offset = time.monotonic, [0]
        def late(name, details):
            if name == "handoff" and details["phase"] == "observed":
                offset[0] = 20
        with patch("routine.local_run.time.monotonic", side_effect=lambda: monotonic() + offset[0]):
            with self.assertRaises(RoutineError) as caught:
                self.prepare(timeout=10, checkpoint=late)
        self.assertEqual(caught.exception.code, "command_timeout")
        self.assertTrue((self.destination / "checkout/.git").is_dir())
        self.assertTrue((self.destination / "handoff/context.json").is_file())

    def test_partial_export_failure_retains_artifacts(self):
        def fail_export(root, commit, destination, **kwargs):
            Path(destination).write_bytes(b"partial-export")
            raise RoutineError("command_timeout", "Fixture export interrupted")
        with patch("routine.local_run.export_bundle", side_effect=fail_export):
            with self.assertRaises(RoutineError):
                self.prepare()
        self.assertEqual((self.destination / "source.bundle").read_bytes(), b"partial-export")
        self.assertFalse((self.destination / "checkout").exists())

    def test_checkout_directory_replacement_is_not_adopted(self):
        prepared = self.prepare()
        checkout = Path(prepared["checkout"])
        moved = self.destination / "original-checkout"
        checkout.rename(moved)
        checkout.mkdir()
        (moved / ".git").rename(checkout / ".git")
        (moved / "app.txt").rename(checkout / "app.txt")
        with self.assertRaises(RoutineError):
            self.verify(prepared)

    def test_sha256_git_repository_clone(self):
        original = self.root
        self.root = self.base / "sha256-project"
        self.root.mkdir()
        self.git("init", "--object-format=sha256", "--template=", str(self.root))
        (self.root / "app.txt").write_text("sha256 fixture\n")
        self.git("-C", str(self.root), "add", "app.txt")
        self.git("-C", str(self.root), "-c", "user.name=Fixture", "-c",
                 "user.email=fixture@example.invalid", "commit", "-m", "Fixture")
        commit = self.git("-C", str(self.root), "rev-parse", "HEAD").decode().strip()
        self.assertEqual(len(commit), 64)
        for baseline in (self.feature["verified_head"], self.feature["package"]["manifest"]["baseline"],
                         self.run["baseline"], self.run["request"]["baseline"]):
            baseline["commit"] = commit
        self.git("-C", str(self.root), "update-ref", self.baseline["branch"], commit)
        snapshots = self.feature["package"]["snapshots"]
        snapshots[".opencode/routine/features/fixture/approval.json"] = canonical(self.feature["package"]["manifest"]).decode()
        for name, text in snapshots.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode())
        self.feature["project_root"] = str(self.root)
        prepared = self.prepare()
        self.assertEqual(prepared["commit"], commit)
        self.verify(prepared)
        self.assertTrue(original.exists())

    def test_artifact_redirection_at_checkpoint_is_not_followed(self):
        unrelated = self.base / "unrelated"
        unrelated.mkdir()
        retained = self.base / "retained"
        def redirect(name, details):
            if name == "artifact" and details["phase"] == "observed":
                self.destination.rename(retained)
                self.destination.symlink_to(unrelated, target_is_directory=True)
        with self.assertRaises(RoutineError):
            self.prepare(checkpoint=redirect)
        self.assertEqual(list(unrelated.iterdir()), [])
        self.assertTrue(retained.is_dir())

    def test_empty_template_is_revalidated_before_clone(self):
        def change_template(name, details):
            if name == "export" and details["phase"] == "observed":
                (self.destination / "empty-template/config").write_text("[include]\npath=/missing\n")
        with self.assertRaises(RoutineError):
            self.prepare(checkpoint=change_template)
        self.assertFalse((self.destination / "checkout").exists())

    def test_late_export_result_is_not_adopted(self):
        from routine.local_run import export_bundle
        monotonic, offset = time.monotonic, [0]
        def late_export(*args, **kwargs):
            result = export_bundle(*args, **kwargs)
            offset[0] = 20
            return result
        with patch("routine.local_run.time.monotonic", side_effect=lambda: monotonic() + offset[0]), \
                patch("routine.local_run.export_bundle", side_effect=late_export):
            with self.assertRaises(RoutineError) as caught:
                self.prepare()
        self.assertEqual(caught.exception.code, "command_timeout")
        self.assertTrue((self.destination / "source.bundle").exists())
        self.assertFalse((self.destination / "checkout").exists())

    def test_directory_entries_are_synced_child_first_before_observed_fences(self):
        original_fsync = os.fsync
        for effect in ("artifact", "export", "clone", "handoff"):
            with self.subTest(effect=effect):
                self.destination = self.base / ("durable-" + effect)
                actions = []
                def sync(descriptor):
                    original_fsync(descriptor)
                    actions.append(("sync", Path(os.readlink(f"/proc/self/fd/{descriptor}"))))
                def checkpoint(name, details):
                    if name == effect and details["phase"] == "observed":
                        # Every current entry must have been synced, with each
                        # containing directory synced after its children.
                        latest = {path: index for index, (kind, path) in enumerate(actions) if kind == "sync"}
                        paths = [self.destination, *self.destination.rglob("*")]
                        for path in paths:
                            self.assertIn(path, latest, str(path))
                            if path.is_dir():
                                for child in path.iterdir():
                                    self.assertGreater(latest[path], latest[child], str(path))
                    actions.append(("checkpoint", name))
                with patch("routine.local_run.os.fsync", side_effect=sync):
                    self.prepare(checkpoint=checkpoint)

    def test_final_publication_resyncs_after_observed_callback(self):
        actions, original_fsync = [], os.fsync
        def sync(descriptor):
            original_fsync(descriptor)
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                actions.append(Path(os.readlink(f"/proc/self/fd/{descriptor}")))
        def checkpoint(name, details):
            if name == "handoff" and details["phase"] == "observed":
                actions.clear()
        with patch("routine.local_run.os.fsync", side_effect=sync):
            self.prepare(checkpoint=checkpoint)
        for path in (self.destination, self.destination / "evidence", self.destination / "handoff",
                     self.destination / "handoff/planning/docs", self.destination / "checkout/.git"):
            self.assertIn(path, actions)

    def test_directory_sync_failure_prevents_observed_publication_and_retains_artifacts(self):
        original_fsync = os.fsync
        for effect in ("export", "handoff"):
            with self.subTest(effect=effect):
                self.destination = self.base / ("sync-failure-" + effect)
                events = []
                def sync(descriptor):
                    path = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
                    fail_export = effect == "export" and path == self.destination and (path / "source.bundle").exists()
                    fail_handoff = effect == "handoff" and path == self.destination / "handoff/planning/docs"
                    if stat.S_ISDIR(os.fstat(descriptor).st_mode) and (fail_export or fail_handoff):
                        raise OSError(errno.EIO, "SECRET_SYNC_CANARY")
                    original_fsync(descriptor)
                with patch("routine.local_run.os.fsync", side_effect=sync):
                    with self.assertRaises(RoutineError) as caught:
                        self.prepare(checkpoint=lambda name, details: events.append((name, details["phase"])))
                self.assertNotIn("SECRET_SYNC_CANARY", str(caught.exception))
                self.assertNotIn((effect, "observed"), events)
                self.assertTrue((self.destination / "source.bundle").is_file())
                if effect == "handoff":
                    self.assertTrue((self.destination / "handoff/planning/docs/spec.md").is_file())
                    self.assertTrue((self.destination / "checkout/.git").is_dir())

    def test_directory_sync_late_return_prevents_observed_publication(self):
        original_fsync, monotonic, offset = os.fsync, time.monotonic, [0]
        events = []
        def sync(descriptor):
            original_fsync(descriptor)
            path = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
            if stat.S_ISDIR(os.fstat(descriptor).st_mode) and path == self.destination / "handoff/planning/docs":
                offset[0] = 20
        with patch("routine.local_run.os.fsync", side_effect=sync), \
                patch("routine.local_run.time.monotonic", side_effect=lambda: monotonic() + offset[0]):
            with self.assertRaises(RoutineError) as caught:
                self.prepare(checkpoint=lambda name, details: events.append((name, details["phase"])))
        self.assertEqual(caught.exception.code, "command_timeout")
        self.assertNotIn(("handoff", "observed"), events)
        self.assertTrue((self.destination / "handoff/planning/docs/spec.md").is_file())


if __name__ == "__main__":
    unittest.main()
