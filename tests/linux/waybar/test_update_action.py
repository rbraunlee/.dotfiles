"""Exercise the update click with inert launchers; never run the upgrade payload."""

import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "linux/waybar/.config/waybar/scripts/update-sys.sh"


class UpdateActionTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory(prefix="waybar-action-")
        self.addCleanup(self.root.cleanup)
        self.home = Path(self.root.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.marker = self.home / "arch-release"
        self.marker.touch()
        self.launch_calls = self.home / "launch-calls"
        self.query_calls = self.home / "query-calls"
        # The fake terminal only records argv; it cannot interpret or execute the payload.
        self.fake("ghostty", 'printf "%s\\n" "$@" > "$WAYBAR_TEST_LAUNCH_CALLS"')
        self.fake("kitty", 'printf "%s\\n" "$@" > "$WAYBAR_TEST_QUERY_CALLS"')
        self.fake("paru", 'printf "paru\\n" >> "$WAYBAR_TEST_QUERY_CALLS"')
        self.fake("checkupdates", 'printf "checkupdates\\n" >> "$WAYBAR_TEST_QUERY_CALLS"')
        self.fake("sh", 'printf "sh\\n" >> "$WAYBAR_TEST_QUERY_CALLS"')

    def fake(self, name, body, status=0):
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n{body}\nexit {status}\n", encoding="utf-8")
        path.chmod(0o700)

    def run_script(self, mode="update"):
        env = {
            "PATH": str(self.bin),
            "HOME": str(self.home),
            "WAYBAR_ARCH_RELEASE_FILE": str(self.marker),
            "WAYBAR_TEST_LAUNCH_CALLS": str(self.launch_calls),
            "WAYBAR_TEST_QUERY_CALLS": str(self.query_calls),
        }
        return subprocess.run(
            ["/bin/bash", str(SCRIPT), mode], env=env, cwd=self.home,
            text=True, capture_output=True, timeout=5, check=False,
        )

    def test_update_launches_ghostty_with_original_title_and_upgrade_without_queries(self):
        result = self.run_script()
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        self.assertEqual(
            self.launch_calls.read_text(encoding="utf-8").splitlines(),
            ["--title=update-sys", "-e", "sh", "-c", "paru -Syu"],
        )
        self.assertFalse(self.query_calls.exists(), "neither providers nor Kitty may be invoked")

    def test_update_does_not_require_checkupdates(self):
        (self.bin / "checkupdates").unlink()
        result = self.run_script()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        self.assertTrue(self.launch_calls.exists())
        self.assertFalse(self.query_calls.exists())

    def test_non_arch_update_does_nothing_even_without_prerequisites(self):
        self.marker.unlink()
        (self.bin / "paru").unlink()
        (self.bin / "ghostty").unlink()
        result = self.run_script()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        self.assertFalse(self.launch_calls.exists())
        self.assertFalse(self.query_calls.exists())

    def test_unrecognized_mode_cannot_launch_or_query(self):
        result = self.run_script("noop")
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        self.assertFalse(self.launch_calls.exists())
        self.assertFalse(self.query_calls.exists())

    def test_missing_upgrade_provider_does_not_launch_a_terminal(self):
        (self.bin / "paru").unlink()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("paru", result.stderr)
        self.assertFalse(self.launch_calls.exists())
        self.assertFalse(self.query_calls.exists())

    def test_missing_command_shell_does_not_launch_a_terminal(self):
        (self.bin / "sh").unlink()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sh", result.stderr)
        self.assertFalse(self.launch_calls.exists())
        self.assertFalse(self.query_calls.exists())

    def test_missing_ghostty_reports_failure_without_fallback(self):
        (self.bin / "ghostty").unlink()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cannot launch updates", result.stderr)
        self.assertIn("Ghostty", result.stderr)
        self.assertFalse(self.launch_calls.exists())
        self.assertFalse(self.query_calls.exists())

    def test_failed_ghostty_launch_reports_failure_without_fallback(self):
        self.fake("ghostty", 'printf "%s\\n" "$@" > "$WAYBAR_TEST_LAUNCH_CALLS"', status=23)
        result = self.run_script()
        self.assertEqual(result.returncode, 23)
        self.assertIn("Ghostty launch failed", result.stderr)
        self.assertEqual(self.launch_calls.read_text(encoding="utf-8").splitlines()[-1], "paru -Syu")
        self.assertFalse(self.query_calls.exists())


if __name__ == "__main__":
    unittest.main()
