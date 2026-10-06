"""Descriptor/provenance contracts on local fixtures; not privileged Docker proof."""
from copy import deepcopy
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_m1 as fixtures
from routine.contracts import RoutineError
from routine.retention import (StorageBinding, confirm_source_unchanged, pin_raw_checkout,
                               production_inspection, source_from_inspection)


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="routine-retention-", dir="/tmp/opencode")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.upper = self.root / "overlay2" / ("a" * 64) / "diff"
        self.lower = self.root / "overlay2" / ("b" * 64) / "diff"
        self.project = self.upper / "home/worker/project"
        (self.project / ".git").mkdir(parents=True)
        (self.project / ".git/HEAD").write_bytes(b"fixture HEAD\n")
        (self.project / "README.md").write_bytes(b"fixture content\n")
        self.lower.mkdir(parents=True)
        self.binding = StorageBinding(str(self.root), "daemon-1")
        self.info = {"ID": "daemon-1", "DockerRootDir": str(self.root), "Driver": "overlay2",
                     "DriverStatus": [["Backing Filesystem", "xfs"]]}
        self.run = {"state": "sandbox-failed", "result": {"container_stopped": True},
                    "container_id": "c" * 64, "artifact_id": "d" * 64, "launch_id": "e" * 32,
                    "runtime_image": "sha256:" + "f" * 64, "resources": {"disk_mb": 128}}
        self.value = {"Id": self.run["container_id"], "Name": "/routine-" + "d" * 32,
                      "Image": self.run["runtime_image"],
                      "Config": {"Labels": {"routine.artifact-id": "d" * 64, "routine.launch-id": "e" * 32}},
                      "State": {"Running": False, "Paused": False, "Restarting": False, "Dead": False,
                                "Pid": 0, "Status": "exited", "StartedAt": "start-1", "FinishedAt": "finish-1"},
                      "HostConfig": {"StorageOpt": {"size": "128M"}},
                      "GraphDriver": {"Name": "overlay2", "Data": {
                          "ID": self.run["container_id"], "UpperDir": str(self.upper), "LowerDir": str(self.lower),
                          "WorkDir": str(self.upper.parent / "work"), "MergedDir": str(self.upper.parent / "merged")}}}
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.addCleanup(os.close, self.fd)

    def source(self, **values):
        return source_from_inspection(self.binding, values.get("info", self.info),
                                      values.get("inspection", self.value), values.get("run", self.run))

    def pin(self, source=None, **values):
        return pin_raw_checkout(self.fd, source or self.source(), owner_uid=os.geteuid(), deadline=100,
                                clock=values.pop("clock", lambda: 0), **values)

    def error(self, code, operation):
        with self.assertRaises(RoutineError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)

    def admission_fails(self, **values):
        with self.assertRaises(RoutineError):
            self.source(**values)

    def scan_fails(self, code, **values):
        def scan():
            with self.pin(**values):
                self.fail("Unsafe checkout was admitted")
        self.error(code, scan)

    @staticmethod
    def fd_count():
        return len(os.listdir('/proc/self/fd'))

    def test_stopped_source_uses_durable_container_and_preparation_identity(self):
        source = self.source()
        self.assertEqual(source.container_id, self.run["container_id"])
        self.assertEqual(source.upper, ("overlay2", "a" * 64, "diff"))
        self.assertEqual(source.max_bytes, 128 * 1024**2)
        self.assertEqual(len(source.checkpoint_sha256), 64)

    def test_legacy_or_nonterminal_runs_cannot_be_implicitly_adopted(self):
        for field in ("container_id", "launch_id", "artifact_id", "runtime_image"):
            value = deepcopy(self.run)
            del value[field]
            self.admission_fails(run=value)
        for state in ("claimed", "preparing", "starting", "running", "sandbox-held"):
            value = deepcopy(self.run)
            value["state"] = state
            self.admission_fails(run=value)
        for stopped in (False, 1, None):
            value = deepcopy(self.run)
            value["result"]["container_stopped"] = stopped
            self.admission_fails(run=value)

    def test_active_ambiguous_or_malformed_container_state_is_denied(self):
        for field, invalid in (("Running", True), ("Running", 0), ("Paused", True), ("Restarting", True),
                               ("Dead", True), ("Pid", 10), ("Pid", False), ("Status", "created"),
                               ("StartedAt", None), ("FinishedAt", "")):
            value = deepcopy(self.value)
            value["State"][field] = invalid
            self.admission_fails(inspection=value)

    def test_ownership_and_quota_must_match_durable_state(self):
        for field, invalid in (("Id", "0" * 64), ("Name", "/unrelated"), ("Image", "sha256:" + "0" * 64)):
            value = deepcopy(self.value)
            value[field] = invalid
            self.admission_fails(inspection=value)
        for field in ("routine.artifact-id", "routine.launch-id"):
            value = deepcopy(self.value)
            value["Config"]["Labels"][field] = "0" * 64
            self.admission_fails(inspection=value)
        value = deepcopy(self.value)
        value["HostConfig"]["StorageOpt"]["size"] = "256M"
        self.admission_fails(inspection=value)

    def test_daemon_root_and_backend_must_match_trusted_binding(self):
        for field, invalid in (("ID", "other-daemon"), ("DockerRootDir", "/another-store"), ("Driver", "overlayfs")):
            value = deepcopy(self.info)
            value[field] = invalid
            self.admission_fails(info=value)
        for root in ("/", "/store/../other", "/store/", "relative", "/store//docker", None):
            self.error("invalid_runtime", lambda: StorageBinding(root, "daemon-1"))

    def test_graph_paths_cannot_escape_alias_or_select_another_layer(self):
        data = self.value["GraphDriver"]["Data"]
        for field, invalid in (("UpperDir", str(self.root / "overlay2/../outside/diff")),
                               ("UpperDir", str(self.upper) + "/"), ("LowerDir", "/outside/diff"),
                               ("LowerDir", str(self.lower) + ":" + str(self.lower)),
                               ("LowerDir", str(self.upper)), ("LowerDir", str(self.lower) + "\n"),
                               ("WorkDir", str(self.lower.parent / "work")), ("MergedDir", str(self.lower.parent / "merged")),
                               ("ID", "0" * 64)):
            value = deepcopy(self.value)
            value["GraphDriver"]["Data"][field] = invalid
            self.admission_fails(inspection=value)
        value = deepcopy(self.value)
        value["GraphDriver"]["Data"]["LowerDir"] = ":".join([data["LowerDir"]] * 129)
        self.admission_fails(inspection=value)

    def test_source_restart_or_changed_graph_checkpoint_invalidates_inspection(self):
        before = self.source()
        for field in ("StartedAt", "FinishedAt"):
            value = deepcopy(self.value)
            value["State"][field] += "-restart"
            after = self.source(inspection=value)
            self.error("recovery_required", lambda: confirm_source_unchanged(before, after))
        confirm_source_unchanged(before, self.source())

    def test_positive_scan_opens_only_readonly_fds_and_exports_no_paths_or_content(self):
        opened = []
        original = os.open
        def observe(path, flags, *args, **kwargs):
            opened.append(flags)
            return original(path, flags, *args, **kwargs)
        before = self.fd_count()
        with patch('routine.retention.os.open', observe), self.pin() as (fd, summary):
            self.assertEqual(summary, {"entries": 3, "logical_bytes": 29})
            head = original('.git/HEAD', os.O_RDONLY, dir_fd=fd)
            try:
                self.assertEqual(os.read(head, 128), b'fixture HEAD\n')
            finally:
                os.close(head)
        self.assertTrue(opened)
        self.assertTrue(all(not flags & (os.O_CREAT | os.O_TRUNC) and flags & os.O_ACCMODE == os.O_RDONLY for flags in opened))
        self.assertEqual(self.fd_count(), before)

    def test_lower_checkout_even_when_empty_is_not_silently_ignored(self):
        (self.lower / 'home/worker/project').mkdir(parents=True)
        self.scan_fails('unsupported_checkout')

    def test_lower_symlink_ancestor_is_denied_even_when_project_would_be_missing(self):
        (self.lower / 'home').symlink_to(self.root, target_is_directory=True)
        self.scan_fails('unsafe_storage')

    def test_missing_lower_layer_is_corruption_not_proof_of_absent_checkout(self):
        self.lower.rename(self.lower.with_name('missing'))
        self.scan_fails('unsafe_storage')

    def test_upper_project_and_ancestor_symlinks_are_not_followed(self):
        for path in (self.project, self.upper / 'home'):
            moved = path.with_name(path.name + '-original')
            path.rename(moved)
            path.symlink_to(moved, target_is_directory=True)
            try:
                self.scan_fails('unsafe_storage')
            finally:
                path.unlink()
                moved.rename(path)

    def test_untrusted_storage_ancestry_permissions_are_denied(self):
        path = self.upper.parent
        path.chmod(0o777)
        try:
            self.scan_fails('unsafe_storage')
        finally:
            path.chmod(0o755)

    def test_whiteout_names_symlinks_and_fifos_are_denied_without_opening_devices(self):
        for kind in ('whiteout', 'symlink', 'fifo'):
            path = self.project / ('.wh.deleted' if kind == 'whiteout' else 'unsafe-entry')
            if kind == 'symlink':
                path.symlink_to('/etc/passwd')
            elif kind == 'fifo':
                os.mkfifo(path)
            else:
                path.write_bytes(b'')
            try:
                self.scan_fails('unsupported_checkout')
            finally:
                path.unlink()

    def test_hardlinked_files_are_not_admitted(self):
        os.link(self.project / 'README.md', self.project / 'hardlink')
        self.scan_fails('unsupported_checkout')

    def test_overlay_metacopy_redirect_opaque_and_whiteout_metadata_are_denied(self):
        for name in ('trusted.overlay.metacopy', 'trusted.overlay.redirect', 'trusted.overlay.opaque',
                     'user.overlay.metacopy', 'user.overlay.whiteout'):
            self.scan_fails('unsupported_checkout', xattrs=lambda fd: [name])

    def test_xattr_visibility_failure_cannot_be_a_clean_metadata_pass(self):
        def denied(fd):
            raise PermissionError('private-storage-canary')
        self.scan_fails('unsafe_storage', xattrs=denied)
        self.scan_fails('unsafe_storage', xattrs=lambda fd: ['name'] * 129)

    def test_logical_byte_entry_and_nesting_bounds_are_enforced(self):
        self.scan_fails('input_limit', source=replace(self.source(), max_bytes=1))
        self.scan_fails('input_limit', max_entries=1)
        nested = self.project
        for _ in range(66):
            nested = nested / 'nested'
            nested.mkdir()
        self.scan_fails('input_limit')

    def test_deadline_failures_close_all_open_descriptors(self):
        before = self.fd_count()
        clock = [0]
        def tick():
            clock[0] += 20
            return clock[0]
        self.scan_fails('command_timeout', clock=tick)
        self.assertEqual(self.fd_count(), before)

    def test_file_replacement_between_stat_and_open_invalidates_scan(self):
        original = os.open
        def replace_entry(path, flags, *args, **kwargs):
            if path == 'README.md':
                replacement = self.project / 'replacement'
                replacement.write_bytes(b'replaced content')
                replacement.replace(self.project / 'README.md')
            return original(path, flags, *args, **kwargs)
        with patch('routine.retention.os.open', replace_entry):
            self.scan_fails('unsafe_storage')

    def test_directory_lease_survives_path_swap_without_switching_to_foreign_checkout(self):
        with self.pin() as (fd, summary):
            self.project.rename(self.project.with_name('original'))
            self.project.symlink_to(self.lower, target_is_directory=True)
            head = os.open('.git/HEAD', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                self.assertEqual(os.read(head, 128), b'fixture HEAD\n')
            finally:
                os.close(head)
        with self.assertRaises(OSError):
            os.fstat(fd)

    def test_mount_boundary_is_checked_even_when_device_number_would_match(self):
        with patch('routine.retention._mount_id', side_effect=[1, 2]):
            self.scan_fails('unsupported_checkout')

    def test_caller_interruption_closes_pinned_checkout_without_touching_files(self):
        before = self.fd_count()
        with self.assertRaises(RuntimeError):
            with self.pin() as (fd, summary):
                raise RuntimeError('interrupted test caller')
        self.assertEqual(self.fd_count(), before)
        self.assertEqual((self.project / 'README.md').read_bytes(), b'fixture content\n')

    def test_production_gate_cannot_be_enabled_with_flags_root_or_fake_evidence(self):
        with patch('routine.retention.os.open') as opened:
            for flags in ({}, {'enabled': True}, {'uid': 0}, {'evidence': {'passed': True}}):
                self.error('storage_inspection_unavailable', lambda: production_inspection(self.run, **flags))
        opened.assert_not_called()


if __name__ == '__main__':
    unittest.main()
