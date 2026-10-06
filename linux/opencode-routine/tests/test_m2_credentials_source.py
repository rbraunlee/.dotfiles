"""Offline trusted-source contracts; disposable fake bytes only."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_m1  # Package-local import setup.
from routine.contracts import RoutineError
from routine.credential_sources import ScopedFileCredentialBroker


class CredentialSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="routine-source-", dir="/tmp/opencode")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / "fake-key"
        self.file.write_bytes(b"fake-source-canary")
        self.file.chmod(0o600)
        self.binding = {"ref": "test-key", "consumer": "service:database", "purpose": "development", "max_bytes": 64}
        self.grants = [{"authorization_id": "a" * 64, "binding": self.binding, "source": "fake-key"}]

    def broker(self, **kwargs):
        return ScopedFileCredentialBroker(self.root, self.grants, **kwargs)

    def test_exact_grant_returns_erasable_buffer_and_does_not_modify_source(self):
        result = self.broker().resolve({"authorization_id": "a" * 64}, self.binding, 1)
        self.assertIs(type(result), bytearray)
        self.assertEqual(result, b"fake-source-canary")
        self.assertEqual(self.file.read_bytes(), result)

    def test_wrong_authorization_consumer_purpose_and_bound_refuse_before_open(self):
        broker = self.broker()
        cases = [({"authorization_id": "b" * 64}, self.binding)]
        cases += [({"authorization_id": "a" * 64}, {**self.binding, key: value}) for key, value in
                  (("consumer", "service:other"), ("purpose", "production"), ("max_bytes", 65), ("ref", "other"))]
        for request, binding in cases:
            with self.subTest(binding=binding), patch("routine.credential_sources.os.open") as opened:
                with self.assertRaises(RoutineError):
                    broker.resolve(request, binding, 1)
                opened.assert_not_called()

    def test_grants_are_snapshotted_and_duplicate_or_unsafe_grants_rejected(self):
        broker = self.broker()
        self.grants[0]["binding"]["ref"] = "changed"
        self.assertEqual(broker.resolve({"authorization_id": "a" * 64}, {**self.binding, "ref": "test-key"}, 1), b"fake-source-canary")
        with self.assertRaises(RoutineError):
            ScopedFileCredentialBroker(self.root, self.grants * 2)
        for source in ("../fake-key", "/fake-key", "folder/../fake-key", "fake-key/", ""):
            with self.subTest(source=source), self.assertRaises(RoutineError):
                ScopedFileCredentialBroker(self.root, [{**self.grants[0], "source": source}])

    def test_symlink_hardlink_fifo_and_permissions_refused(self):
        broker = self.broker()
        self.file.rename(self.root / "original")
        self.file.symlink_to(self.root / "original")
        with self.assertRaises(RoutineError):
            broker.resolve({"authorization_id": "a" * 64}, self.binding, 1)
        self.file.unlink()
        os.link(self.root / "original", self.file)
        with self.assertRaises(RoutineError):
            broker.resolve({"authorization_id": "a" * 64}, self.binding, 1)
        self.file.unlink()
        os.mkfifo(self.file, 0o600)
        with self.assertRaises(RoutineError):
            broker.resolve({"authorization_id": "a" * 64}, self.binding, 1)
        self.file.unlink()
        (self.root / "original").rename(self.file)
        self.file.chmod(0o644)
        with self.assertRaises(RoutineError):
            broker.resolve({"authorization_id": "a" * 64}, self.binding, 1)

    def test_private_root_identity_symlink_and_mode_changes_refused(self):
        broker = self.broker()
        self.root.chmod(0o755)
        with self.assertRaises(RoutineError):
            broker.resolve({"authorization_id": "a" * 64}, self.binding, 1)
        self.root.chmod(0o700)
        original = self.root / "original"
        original.mkdir()
        # Pinning happens without reading the secret at construction.
        moved = self.root.with_name(self.root.name + "-moved")
        self.root.rename(moved)
        try:
            self.root.mkdir(mode=0o700)
            (self.root / "fake-key").write_bytes(b"foreign")
            with self.assertRaises(RoutineError):
                broker.resolve({"authorization_id": "a" * 64}, self.binding, 1)
        finally:
            (self.root / "fake-key").unlink()
            self.root.rmdir()
            moved.rename(self.root)

    def test_empty_oversized_and_expired_reads_fail_without_returning_bytes(self):
        for value in (b"", b"x" * 65):
            self.file.write_bytes(value)
            with self.assertRaises(RoutineError):
                self.broker().resolve({"authorization_id": "a" * 64}, self.binding, 1)
        for timeout in (0, -1, True, float("nan")):
            with self.assertRaises(RoutineError):
                self.broker().resolve({"authorization_id": "a" * 64}, self.binding, timeout)

    def test_late_read_wipes_buffer_and_closes_descriptors(self):
        clock = [0]
        broker = self.broker(monotonic=lambda: clock[0])
        read = os.readv
        buffers = []
        def late(fd, size):
            value = read(fd, size)
            clock[0] = 2
            return value
        def wipe(value):
            buffers.append(value)
            value[:] = b"\0" * len(value)
        before = len(list(Path("/proc/self/fd").iterdir()))
        with patch("routine.credential_sources.os.readv", side_effect=late), patch("routine.credential_sources.erase", side_effect=wipe):
            with self.assertRaises(RoutineError):
                broker.resolve({"authorization_id": "a" * 64}, self.binding, 1)
        self.assertTrue(buffers)
        self.assertTrue(all(not any(value) for value in buffers))
        self.assertEqual(before, len(list(Path("/proc/self/fd").iterdir())))

    def test_source_mutation_during_read_is_rejected(self):
        broker = self.broker()
        read = os.readv
        def mutate(fd, size):
            value = read(fd, size)
            self.file.write_bytes(b"other-fake-canary")
            return value
        with patch("routine.credential_sources.os.readv", side_effect=mutate), self.assertRaises(RoutineError):
            broker.resolve({"authorization_id": "a" * 64}, self.binding, 1)

    def test_plan_binding_metadata_is_validated_and_never_becomes_a_source_path(self):
        binding = {**self.binding, "target": "/run/credentials/service/database/test-key", "delivery": "read-only-file"}
        self.assertEqual(self.broker().resolve({"authorization_id": "a" * 64}, binding, 1), b"fake-source-canary")
        for extra in ({"source": "fake-key"}, {"target": "/etc/passwd"}, {"delivery": "environment"}):
            with self.assertRaises(RoutineError):
                self.broker().resolve({"authorization_id": "a" * 64}, {**binding, **extra}, 1)

    def test_nested_private_source_and_exact_model_grant(self):
        directory = self.root / "nested"
        directory.mkdir(mode=0o700)
        self.file.rename(directory / "fake-key")
        binding = {**self.binding, "consumer": "provider:openai", "purpose": "model"}
        broker = ScopedFileCredentialBroker(self.root, [{"authorization_id": "a" * 64, "binding": binding, "source": "nested/fake-key"}])
        self.assertEqual(broker.resolve({"authorization_id": "a" * 64}, binding, 1), b"fake-source-canary")
        directory.chmod(0o755)
        with self.assertRaises(RoutineError):
            broker.resolve({"authorization_id": "a" * 64}, binding, 1)

    def test_source_directory_symlink_never_follows_to_secret(self):
        broker = ScopedFileCredentialBroker(self.root, [{**self.grants[0], "source": "nested/fake-key"}])
        (self.root / "nested").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(RoutineError):
            broker.resolve({"authorization_id": "a" * 64}, self.binding, 1)

    def test_os_error_diagnostics_do_not_export_fake_canary(self):
        broker = self.broker()
        with patch("routine.credential_sources.os.readv", side_effect=OSError("fake-source-canary")):
            with self.assertRaises(RoutineError) as error:
                broker.resolve({"authorization_id": "a" * 64}, self.binding, 1)
        self.assertNotIn("fake-source-canary", str(error.exception))

    def test_path_replacement_during_read_cannot_return_a_pass(self):
        broker = self.broker()
        read = os.readv
        replaced = [False]
        def replace(fd, size):
            value = read(fd, size)
            if not replaced[0]:
                replaced[0] = True
                self.file.rename(self.root / "retained-original")
                self.file.write_bytes(b"fake-foreign-source")
                self.file.chmod(0o600)
            return value
        with patch("routine.credential_sources.os.readv", side_effect=replace), self.assertRaises(RoutineError):
            broker.resolve({"authorization_id": "a" * 64}, self.binding, 1)
