"""Run the Waybar count interface with isolated, inert command providers."""

import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "linux/waybar/.config/waybar/scripts/update-sys.sh"


class UpdateCountTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory(prefix="waybar-counts-")
        self.addCleanup(self.root.cleanup)
        self.home = Path(self.root.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        (self.bin / "wc").symlink_to("/usr/bin/wc")
        self.marker = self.home / "arch-release"
        self.marker.touch()
        self.calls = self.home / "calls"
        self.provider("yay", "aur-pkg 1 -> 2\n")
        self.provider("checkupdates", "official-pkg 1 -> 2\n")

    def provider(self, name, output="", status=0):
        path = self.bin / name
        path.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' {shlex.quote(name)} >> {shlex.quote(str(self.calls))}\n"
            f"printf '%s' {shlex.quote(output)}\n"
            f"exit {status}\n",
            encoding="utf-8",
        )
        path.chmod(0o700)

    def run_script(self, mode=None):
        env = {
            "PATH": str(self.bin),
            "HOME": str(self.home),
            "WAYBAR_ARCH_RELEASE_FILE": str(self.marker),
        }
        return subprocess.run(
            ["/bin/bash", str(SCRIPT), *([mode] if mode is not None else [])],
            env=env, cwd=self.home, text=True, capture_output=True, timeout=5,
            check=False,
        )

    def test_non_arch_count_modes_do_not_query_providers(self):
        self.marker.unlink()
        for mode in (None, "aur", "official"):
            with self.subTest(mode=mode):
                result = self.run_script(mode)
                self.assertEqual((result.returncode, result.stdout, self.calls.exists()), (0, "", False))

    def test_combined_count_retains_icon_and_total(self):
        self.provider("yay", "aur-one 1 -> 2\naur-two 3 -> 4\n")
        result = self.run_script()
        self.assertEqual((result.returncode, result.stdout), (0, " 3\n"))

    def test_empty_successful_queries_leave_bar_blank(self):
        self.provider("yay")
        self.provider("checkupdates")
        result = self.run_script()
        self.assertEqual((result.returncode, result.stdout), (0, "\n"))

    def test_official_no_updates_status_two_is_not_a_failure(self):
        self.provider("checkupdates", status=2)
        result = self.run_script()
        self.assertEqual((result.returncode, result.stdout), (0, " 1\n"))

    def test_failing_aur_must_not_show_partial_official_count(self):
        self.provider("yay", "provider error\n", status=1)
        result = self.run_script()
        self.assertEqual((result.returncode, result.stdout), (0, "Updates unavailable\n"))

    def test_failing_official_must_not_show_partial_aur_count(self):
        self.provider("checkupdates", "provider error\n", status=1)
        result = self.run_script()
        self.assertEqual((result.returncode, result.stdout), (0, "Updates unavailable\n"))

    def test_missing_aur_is_unavailable(self):
        (self.bin / "yay").unlink()
        result = self.run_script()
        self.assertEqual((result.returncode, result.stdout), (0, "Updates unavailable\n"))

    def test_missing_official_is_unavailable(self):
        (self.bin / "checkupdates").unlink()
        result = self.run_script()
        self.assertEqual((result.returncode, result.stdout), (0, "Updates unavailable\n"))

    def test_aur_status_two_is_not_official_no_updates(self):
        self.provider("yay", status=2)
        result = self.run_script()
        self.assertEqual((result.returncode, result.stdout), (0, "Updates unavailable\n"))

    def test_official_no_updates_status_must_not_mask_diagnostics(self):
        self.provider("checkupdates", "database not available\n", status=2)
        result = self.run_script()
        self.assertEqual((result.returncode, result.stdout), (0, "Updates unavailable\n"))

    def test_official_no_updates_status_with_listed_updates_is_invalid(self):
        self.provider("checkupdates", "official-pkg 1 -> 2\n", status=2)
        result = self.run_script()
        self.assertEqual((result.returncode, result.stdout), (0, "Updates unavailable\n"))

    def test_aur_mode_requires_only_aur_and_preserves_icon(self):
        (self.bin / "checkupdates").unlink()
        self.provider("yay", "one 1 -> 2\ntwo 3 -> 4\n")
        result = self.run_script("aur")
        self.assertEqual((result.returncode, result.stdout), (0, " 2\n"))
        self.assertEqual(self.calls.read_text().splitlines(), ["yay"])

    def test_official_mode_requires_only_official_and_preserves_zero_icon(self):
        (self.bin / "yay").unlink()
        self.provider("checkupdates", status=2)
        result = self.run_script("official")
        self.assertEqual((result.returncode, result.stdout), (0, " 0\n"))
        self.assertEqual(self.calls.read_text().splitlines(), ["checkupdates"])

    def test_official_mode_preserves_positive_count(self):
        self.provider("checkupdates", "first 1 -> 2\nsecond 2 -> 3\n")
        result = self.run_script("official")
        self.assertEqual((result.returncode, result.stdout), (0, " 2\n"))

    def test_named_mode_failed_provider_is_unavailable(self):
        self.provider("yay", status=1)
        result = self.run_script("aur")
        self.assertEqual((result.returncode, result.stdout), (0, "Updates unavailable\n"))

    def test_successful_query_diagnostic_stdout_is_not_a_count(self):
        self.provider("checkupdates", "warning: cache corrupt\n")
        result = self.run_script()
        self.assertEqual((result.returncode, result.stdout), (0, "Updates unavailable\n"))

    def test_successful_aur_query_with_blank_line_is_not_a_count(self):
        self.provider("yay", "aur-pkg 1 -> 2\n\nother-pkg 1 -> 2\n")
        result = self.run_script("aur")
        self.assertEqual((result.returncode, result.stdout), (0, "Updates unavailable\n"))


if __name__ == "__main__":
    unittest.main()
