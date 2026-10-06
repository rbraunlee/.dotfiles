"""W1 bundle fixtures only: no installation, sessions, commands or live state."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

LIBRARY = Path(__file__).resolve().parents[1] / ".local/lib/opencode-routine"
sys.path.insert(0, str(LIBRARY))

from routine.contracts import RoutineError, canonical, digest
from routine import local_bundle


class W1BundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="routine-w1-bundle-", dir="/tmp/opencode")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "bundle"
        self.root.mkdir()
        self.files = {
            "agents/builder.md": b"# Builder\nOne slice only.\n",
            "skills/tdd/SKILL.md": b"# TDD\n",
            "skills/tdd/resources/example.txt": b"red then green\n",
            "provenance.md": b"Locally owned fixture; no upstream runtime dependency.\n",
        }
        for name, data in self.files.items():
            self.write(name, data)
        self.destination = self.base / "snapshot"

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def describe(self, **kwargs):
        return local_bundle.describe_bundle(self.root, max_bytes=kwargs.get("max_bytes", 4096),
                                            timeout=kwargs.get("timeout", 30))

    def snapshot(self, expected=None, **kwargs):
        expected = expected or self.describe()["sha256"]
        return local_bundle.snapshot_bundle(self.root, self.destination, expected,
                                            max_bytes=kwargs.get("max_bytes", 4096),
                                            timeout=kwargs.get("timeout", 30))

    def verify(self, expected, **kwargs):
        return local_bundle.verify_snapshot(self.destination, expected,
                                            max_bytes=kwargs.get("max_bytes", 4096),
                                            timeout=kwargs.get("timeout", 30))

    def expect_error(self, code, operation):
        with self.assertRaises(RoutineError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)

    def test_identity_is_canonical_sorted_exact_path_hash_inventory(self):
        self.write("skills/tdd/resources/é.txt", b"resource bytes\x00\xff")
        self.files["skills/tdd/resources/é.txt"] = b"resource bytes\x00\xff"
        inventory = [{"path": name, "sha256": digest(data)} for name, data in sorted(self.files.items())]
        expected = {"sha256": digest(canonical(inventory)), "inventory": inventory}
        self.assertEqual(self.describe(), expected)
        self.assertEqual(self.describe(), expected)

    def test_snapshot_copies_bytes_and_returns_verified_identity(self):
        expected = self.describe()
        self.assertEqual(self.snapshot(expected["sha256"]), expected)
        self.assertEqual(self.verify(expected["sha256"]), expected)
        for name, data in self.files.items():
            copied = self.destination / name
            self.assertFalse(copied.is_symlink())
            self.assertEqual(copied.read_bytes(), data)
            self.assertNotEqual(copied.stat().st_ino, (self.root / name).stat().st_ino)

    def test_source_edits_do_not_change_frozen_snapshot(self):
        expected = self.snapshot()
        self.write("agents/builder.md", b"new global prompt")
        self.write("skills/tdd/resources/new.txt", b"future feature only")
        self.assertNotEqual(self.describe()["sha256"], expected["sha256"])
        self.assertEqual(self.verify(expected["sha256"]), expected)

    def test_missing_provenance_is_rejected(self):
        (self.root / "provenance.md").unlink()
        self.expect_error("invalid_input", self.describe)

    def test_missing_agent_entries_is_rejected(self):
        (self.root / "agents/builder.md").unlink()
        self.expect_error("invalid_input", self.describe)

    def test_missing_skill_definition_is_rejected(self):
        (self.root / "skills/tdd/SKILL.md").unlink()
        self.expect_error("invalid_input", self.describe)

    def test_each_selected_skill_needs_a_definition(self):
        self.write("skills/other/resources/readme.md", b"not a skill definition")
        self.expect_error("invalid_input", self.describe)

    def test_unrelated_root_files_are_not_silently_ignored(self):
        self.write("config.json", b"unreviewed runtime configuration")
        self.expect_error("invalid_input", self.describe)

    def test_agents_are_direct_markdown_files(self):
        self.write("agents/nested/agent.md", b"unexpected layout")
        self.expect_error("invalid_input", self.describe)

    def test_source_installation_file_link_resolves_to_copied_regular_bytes(self):
        target = self.base / "installed-agent.md"
        target.write_bytes(self.files["agents/builder.md"])
        agent = self.root / "agents/builder.md"
        agent.unlink()
        agent.symlink_to(target)
        expected = self.describe()
        self.assertEqual(self.snapshot(expected["sha256"]), expected)
        target.write_bytes(b"later installation edits")
        self.assertEqual(self.verify(expected["sha256"]), expected)

    def test_relative_source_file_link_is_supported(self):
        target = self.base / "agent.md"
        target.write_bytes(self.files["agents/builder.md"])
        agent = self.root / "agents/builder.md"
        agent.unlink()
        agent.symlink_to("../../agent.md")
        self.assertEqual(self.describe()["inventory"][0]["sha256"], digest(target.read_bytes()))

    def test_directory_links_are_rejected(self):
        resources = self.root / "skills/tdd/resources"
        resources.rename(self.base / "resources")
        resources.symlink_to(self.base / "resources", target_is_directory=True)
        self.expect_error("invalid_path", self.describe)

    def test_root_and_ancestor_directory_links_are_rejected(self):
        linked = self.base / "linked"
        linked.symlink_to(self.root, target_is_directory=True)
        self.expect_error("invalid_path", lambda: local_bundle.describe_bundle(linked, max_bytes=4096, timeout=30))
        parent = self.base / "linked-parent"
        parent.symlink_to(self.base, target_is_directory=True)
        self.expect_error("invalid_path", lambda: local_bundle.describe_bundle(parent / "bundle", max_bytes=4096, timeout=30))

    def test_fifo_is_rejected_without_blocking(self):
        os.mkfifo(self.root / "skills/tdd/resources/fifo")
        self.expect_error("invalid_input", self.describe)

    def test_file_link_to_fifo_is_rejected_without_blocking(self):
        fifo = self.base / "fifo"
        os.mkfifo(fifo)
        self.write("skills/tdd/resources/link", b"")
        link = self.root / "skills/tdd/resources/link"
        link.unlink()
        link.symlink_to(fifo)
        self.expect_error("invalid_input", self.describe)

    def test_hardlinks_are_rejected(self):
        os.link(self.root / "agents/builder.md", self.base / "hardlink")
        self.expect_error("invalid_input", self.describe)

    def test_source_file_link_to_hardlinked_target_is_rejected(self):
        target = self.base / "installed-agent.md"
        target.write_bytes(self.files["agents/builder.md"])
        os.link(target, self.base / "another-name")
        agent = self.root / "agents/builder.md"
        agent.unlink()
        agent.symlink_to(target)
        self.expect_error("invalid_input", self.describe)

    def test_snapshot_exclusively_creates_destination(self):
        self.destination.mkdir()
        canary = self.destination / "canary"
        canary.write_bytes(b"preserve")
        self.expect_error("artifact_exists", self.snapshot)
        self.assertEqual(canary.read_bytes(), b"preserve")

    def test_concurrent_snapshot_creation_has_exactly_one_success(self):
        expected = self.describe()["sha256"]

        def attempt(_):
            try:
                return self.snapshot(expected)
            except RoutineError as exc:
                return exc.code

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(8)))
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(results.count("artifact_exists"), 7)
        self.assertEqual(self.verify(expected)["sha256"], expected)

    def test_destination_link_is_not_followed_or_replaced(self):
        other = self.base / "other"
        other.mkdir()
        self.destination.symlink_to(other, target_is_directory=True)
        self.expect_error("artifact_exists", self.snapshot)
        self.assertTrue(self.destination.is_symlink())
        self.assertEqual(list(other.iterdir()), [])

    def test_snapshot_inside_source_is_rejected_without_mutating_source(self):
        self.destination = self.root / "snapshot"
        self.expect_error("invalid_path", self.snapshot)
        self.assertFalse(self.destination.exists())

    def test_changed_source_identity_retains_unpublished_copy(self):
        expected = self.describe()["sha256"]
        self.write("agents/builder.md", b"unapproved")
        self.expect_error("changed_input", lambda: self.snapshot(expected))
        self.assertTrue(self.destination.is_dir())
        self.assertTrue(list(self.destination.rglob("*")))

    def test_snapshot_changed_bytes_additions_and_omissions_are_rejected(self):
        self.write("skills/tdd/resources/remaining.txt", b"keep the resource directory nonempty")
        expected = self.snapshot()["sha256"]
        agent = self.destination / "agents/builder.md"
        agent.chmod(0o600)
        agent.write_bytes(b"changed bytes")
        self.expect_error("changed_input", lambda: self.verify(expected))
        agent.write_bytes(self.files["agents/builder.md"])
        extra = self.destination / "skills/tdd/resources/extra.txt"
        extra.write_bytes(b"added")
        self.expect_error("changed_input", lambda: self.verify(expected))
        extra.unlink()
        (self.destination / "skills/tdd/resources/example.txt").unlink()
        self.expect_error("changed_input", lambda: self.verify(expected))

    def test_snapshot_file_links_are_rejected_even_with_matching_bytes(self):
        expected = self.snapshot()["sha256"]
        agent = self.destination / "agents/builder.md"
        agent.unlink()
        agent.symlink_to(self.root / "agents/builder.md")
        self.expect_error("invalid_path", lambda: self.verify(expected))

    def test_snapshot_directory_links_and_empty_additions_are_rejected(self):
        expected = self.snapshot()["sha256"]
        extra = self.destination / "skills/tdd/resources/extra"
        extra.mkdir()
        self.expect_error("invalid_input", lambda: self.verify(expected))
        extra.rmdir()
        resources = self.destination / "skills/tdd/resources"
        resources.rename(self.base / "copied-resources")
        resources.symlink_to(self.base / "copied-resources", target_is_directory=True)
        self.expect_error("invalid_path", lambda: self.verify(expected))

    def test_total_content_byte_budget_not_just_per_file_budget(self):
        total = sum(map(len, self.files.values()))
        self.assertEqual(self.describe(max_bytes=total)["sha256"], self.describe()["sha256"])
        self.expect_error("input_limit", lambda: self.describe(max_bytes=total - 1))
        expected = self.describe()["sha256"]
        self.expect_error("input_limit", lambda: self.snapshot(expected, max_bytes=total - 1))
        self.assertTrue(self.destination.is_dir())

    def test_verify_is_byte_bounded(self):
        expected = self.snapshot()["sha256"]
        self.expect_error("input_limit", lambda: self.verify(expected, max_bytes=1))

    def test_invalid_limits_and_hashes_are_rejected_before_creation(self):
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit):
                self.expect_error("invalid_input", lambda: self.describe(max_bytes=limit))
        for timeout in (0, -1, True, float("inf"), float("nan"), 10 ** 400):
            with self.subTest(timeout=timeout):
                self.expect_error("invalid_input", lambda: self.describe(timeout=timeout))
        self.expect_error("invalid_input", lambda: self.snapshot("not-a-sha256"))
        self.assertFalse(self.destination.exists())

    def test_expired_deadline_is_rejected(self):
        with patch.object(local_bundle.time, "monotonic", side_effect=[0, 100]):
            self.expect_error("command_timeout", self.describe)

    def test_verify_deadline_is_checked(self):
        expected = self.snapshot()["sha256"]
        with patch.object(local_bundle.time, "monotonic", side_effect=[0, 100]):
            self.expect_error("command_timeout", lambda: self.verify(expected))

    def test_timeout_during_copy_retains_partial_files(self):
        expected = self.describe()["sha256"]
        expired = False
        real_write = os.write

        def write_then_expire(*args):
            nonlocal expired
            result = real_write(*args)
            expired = True
            return result

        with patch.object(local_bundle.time, "monotonic", side_effect=lambda: 100 if expired else 0):
            with patch.object(local_bundle.os, "write", side_effect=write_then_expire):
                self.expect_error("command_timeout", lambda: self.snapshot(expected))
        self.assertTrue(self.destination.is_dir())
        self.assertTrue(any(path.is_file() for path in self.destination.rglob("*")))
        with self.assertRaises(RoutineError):
            self.verify(expected)

    def test_partial_writes_are_completed_and_verified(self):
        expected = self.describe()["sha256"]
        real_write = os.write

        def partial_write(fd, data):
            return real_write(fd, data[:2])

        with patch.object(local_bundle.os, "write", side_effect=partial_write):
            self.assertEqual(self.snapshot(expected)["sha256"], expected)
        self.assertEqual(self.verify(expected)["sha256"], expected)

    def test_racy_file_mutation_is_rejected(self):
        real_read = os.read
        mutated = False

        def read_then_mutate(*args):
            nonlocal mutated
            data = real_read(*args)
            if data and not mutated:
                mutated = True
                self.write("agents/builder.md", b"changed during read")
            return data

        with patch.object(local_bundle.os, "read", side_effect=read_then_mutate):
            self.expect_error("changed_input", self.describe)

    def test_racy_file_replacement_with_matching_bytes_is_rejected(self):
        real_read = os.read
        replaced = False

        def read_then_replace(*args):
            nonlocal replaced
            data = real_read(*args)
            if data and not replaced:
                replaced = True
                (self.root / "agents/builder.md").rename(self.base / "old-agent.md")
                self.write("agents/builder.md", self.files["agents/builder.md"])
            return data

        with patch.object(local_bundle.os, "read", side_effect=read_then_replace):
            self.expect_error("changed_input", self.describe)

    def test_previously_read_file_is_revalidated_at_end(self):
        real_read = os.read
        mutated = False

        def read_then_mutate_previous(fd, size):
            nonlocal mutated
            data = real_read(fd, size)
            if data and not mutated and os.readlink(f"/proc/self/fd/{fd}").endswith("provenance.md"):
                mutated = True
                self.write("agents/builder.md", b"mutated after this file was read")
            return data

        with patch.object(local_bundle.os, "read", side_effect=read_then_mutate_previous):
            self.expect_error("changed_input", self.describe)
        self.assertTrue(mutated)

    def test_source_ancestor_sibling_creation_during_open_is_allowed(self):
        expected = self.describe()
        real_open = os.open
        created = False

        def open_then_create_sibling(*args, **kwargs):
            nonlocal created
            descriptor = real_open(*args, **kwargs)
            if not created and os.readlink(f"/proc/self/fd/{descriptor}") == str(self.base):
                created = True
                (self.base / "local-inspect-source").mkdir()
            return descriptor

        with patch.object(local_bundle.os, "open", side_effect=open_then_create_sibling):
            self.assertEqual(self.describe(), expected)
        self.assertTrue(created)

    def test_snapshot_ancestor_sibling_creation_during_open_is_allowed(self):
        expected = self.snapshot()
        real_open = os.open
        created = False

        def open_then_create_sibling(*args, **kwargs):
            nonlocal created
            descriptor = real_open(*args, **kwargs)
            if not created and os.readlink(f"/proc/self/fd/{descriptor}") == str(self.base):
                created = True
                (self.base / "local-inspect-snapshot").mkdir()
            return descriptor

        with patch.object(local_bundle.os, "open", side_effect=open_then_create_sibling):
            self.assertEqual(self.verify(expected["sha256"]), expected)
        self.assertTrue(created)

    def test_ancestor_sibling_creation_during_content_reads_is_allowed(self):
        expected = self.snapshot()
        real_read = os.read
        sequence = 0

        def read_then_create_sibling(*args):
            nonlocal sequence
            data = real_read(*args)
            sequence += 1
            (self.base / f"local-inspect-{sequence}").mkdir()
            return data

        with patch.object(local_bundle.os, "read", side_effect=read_then_create_sibling):
            self.assertEqual(self.describe(), expected)
            self.assertEqual(self.verify(expected["sha256"]), expected)

    def test_racy_directory_replacement_is_rejected(self):
        real_read = os.read
        replaced = False

        def read_then_replace(*args):
            nonlocal replaced
            data = real_read(*args)
            if data and not replaced:
                replaced = True
                (self.root / "agents").rename(self.base / "old-agents")
                self.write("agents/builder.md", self.files["agents/builder.md"])
            return data

        with patch.object(local_bundle.os, "read", side_effect=read_then_replace):
            self.expect_error("changed_input", self.describe)

    def test_addition_during_traversal_is_rejected(self):
        real_read = os.read
        mutated = False

        def read_then_add(*args):
            nonlocal mutated
            data = real_read(*args)
            if data and not mutated:
                mutated = True
                self.write("skills/tdd/resources/added.txt", b"concurrent addition")
            return data

        with patch.object(local_bundle.os, "read", side_effect=read_then_add):
            self.expect_error("changed_input", self.describe)

    def test_copied_bytes_are_reread_before_success(self):
        expected = self.describe()["sha256"]
        real_fsync = os.fsync
        corrupted = False

        def fsync_then_corrupt(fd):
            nonlocal corrupted
            result = real_fsync(fd)
            copied = self.destination / "agents/builder.md"
            if copied.exists() and not corrupted:
                corrupted = True
                copied.chmod(0o600)
                copied.write_bytes(b"copy corrupted before return")
            return result

        with patch.object(local_bundle.os, "fsync", side_effect=fsync_then_corrupt):
            self.expect_error("changed_input", lambda: self.snapshot(expected))
        self.assertTrue(corrupted)
        self.assertTrue(self.destination.is_dir())


if __name__ == "__main__":
    unittest.main()
