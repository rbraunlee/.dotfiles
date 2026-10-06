"""Configuration-blind W1 Git inspection; disposable repositories only."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".local/lib/opencode-routine"))

from routine.contracts import RoutineError


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="w1-baseline-", dir="/tmp/opencode")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self.git("init", "--template=", str(self.root))
        self.git("-C", str(self.root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "--allow-empty", "-m", "Fixture")
        self.commit = self.git("-C", str(self.root), "rev-parse", "HEAD").strip().decode()
        self.baseline = {"commit": self.commit, "branch": "refs/heads/features/fixture"}
        self.git("-C", str(self.root), "update-ref", self.baseline["branch"], self.commit)

    def git(self, *args):
        return subprocess.run(["/usr/bin/git", *args], check=True, capture_output=True,
                              env={"PATH": "/usr/bin:/bin", "HOME": str(self.base),
                                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}).stdout

    def inspect(self):
        from routine.local_baseline import inspect_baseline

        return inspect_baseline(self.root, self.baseline, timeout=5, max_bytes=1024 * 1024,
                                temporary_root=self.base)

    def test_loose_and_packed_ref(self):
        self.assertEqual(self.inspect(), self.baseline)
        self.git("-C", str(self.root), "pack-refs", "--all")
        self.assertEqual(self.inspect(), self.baseline)

    def test_moved_missing_and_noncommit_baseline(self):
        self.baseline["commit"] = "a" * 40
        with self.assertRaises(RoutineError):
            self.inspect()
        self.baseline["commit"] = self.commit
        (self.root / ".git" / self.baseline["branch"]).unlink()
        with self.assertRaises(RoutineError):
            self.inspect()
        blob = self.git("-C", str(self.root), "hash-object", "-w", "--stdin").strip().decode()
        self.baseline["commit"] = blob
        path = self.root / ".git" / self.baseline["branch"]
        path.write_text(blob + "\n")
        with self.assertRaises(RoutineError):
            self.inspect()

    def test_ignores_source_and_ambient_executable_config(self):
        canary = self.base / "executed"
        hook = self.base / "hook"
        hook.write_text(f"#!/bin/sh\ntouch {canary}\n")
        hook.chmod(0o755)
        (self.root / ".git/config").write_text(
            f"[core]\nfsmonitor = {hook}\nhooksPath = {self.base}\n"
            f"[include]\npath = {self.base}/missing-config\n")
        original = os.environ.get("GIT_CONFIG_COUNT")
        os.environ["GIT_CONFIG_COUNT"] = "invalid"
        try:
            self.assertEqual(self.inspect(), self.baseline)
        finally:
            if original is None:
                os.environ.pop("GIT_CONFIG_COUNT", None)
            else:
                os.environ["GIT_CONFIG_COUNT"] = original
        self.assertFalse(canary.exists())

    def test_ref_symlink_and_alternates_fail_closed(self):
        ref = self.root / ".git" / self.baseline["branch"]
        saved = self.base / "ref"
        saved.write_bytes(ref.read_bytes())
        ref.unlink()
        ref.symlink_to(saved)
        with self.assertRaises(RoutineError):
            self.inspect()
        ref.unlink()
        ref.write_bytes(saved.read_bytes())
        (self.root / ".git/objects/info/alternates").write_text("/nonexistent\n")
        with self.assertRaises(RoutineError):
            self.inspect()

    def test_ref_move_during_commit_inspection_is_not_a_pass(self):
        from routine.local_baseline import run_bounded

        def move_ref(argv, **kwargs):
            result = run_bounded(argv, **kwargs)
            if "cat-file" in argv:
                (self.root / ".git" / self.baseline["branch"]).write_text("f" * 40 + "\n")
            return result

        with patch("routine.local_baseline.run_bounded", side_effect=move_ref):
            with self.assertRaises(RoutineError):
                self.inspect()

    def test_sha256_repository_baseline(self):
        root = self.base / "sha256"
        root.mkdir()
        self.git("init", "--object-format=sha256", "--template=", str(root))
        self.git("-C", str(root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "--allow-empty", "-m", "Fixture")
        self.root = root
        self.commit = self.git("-C", str(root), "rev-parse", "HEAD").strip().decode()
        self.assertEqual(len(self.commit), 64)
        self.baseline["commit"] = self.commit
        self.git("-C", str(root), "update-ref", self.baseline["branch"], self.commit)
        self.assertEqual(self.inspect(), self.baseline)

    def test_annotated_tag_is_not_an_exact_commit_anchor(self):
        self.git("-C", str(self.root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "tag", "-a", "fixture-tag", "-m", "Fixture", self.commit)
        tag = self.git("-C", str(self.root), "rev-parse", "fixture-tag").strip().decode()
        self.assertEqual(self.git("-C", str(self.root), "cat-file", "-t", tag), b"tag\n")
        self.baseline["commit"] = tag
        (self.root / ".git" / self.baseline["branch"]).write_text(tag + "\n")
        with self.assertRaises(RoutineError):
            self.inspect()

    def test_symlinked_loose_object_storage_is_rejected(self):
        objects = self.root / ".git/objects"
        prefix = objects / self.commit[:2]
        detached = self.base / "detached-prefix"
        prefix.rename(detached)
        prefix.symlink_to(detached, target_is_directory=True)
        with self.assertRaises(RoutineError):
            self.inspect()
        prefix.unlink()
        detached.rename(prefix)
        loose = prefix / self.commit[2:]
        detached_object = self.base / "detached-object"
        loose.rename(detached_object)
        loose.symlink_to(detached_object)
        with self.assertRaises(RoutineError):
            self.inspect()

    def test_symlinked_pack_storage_is_rejected(self):
        self.git("-C", str(self.root), "repack", "-ad")
        pack = self.root / ".git/objects/pack"
        detached = self.base / "detached-pack"
        pack.rename(detached)
        pack.symlink_to(detached, target_is_directory=True)
        with self.assertRaises(RoutineError):
            self.inspect()
        pack.unlink()
        detached.rename(pack)
        packed_object = next(pack.glob("*.pack"))
        detached_object = self.base / "detached-packed-object"
        packed_object.rename(detached_object)
        packed_object.symlink_to(detached_object)
        with self.assertRaises(RoutineError):
            self.inspect()
