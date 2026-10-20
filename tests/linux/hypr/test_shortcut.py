"""Exercise the real Hyprland Lua config against a no-desktop API double."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "linux/hypr/.config/hypr/hyprland.lua"
PROBE = Path(__file__).with_name("probe.lua")


class HyprlandShortcutTests(unittest.TestCase):
    def run_probe(self, case):
        result = subprocess.run(
            ["lua", str(PROBE), str(CONFIG), case],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_existing_shortcut_dispatches_only_interactive_flameshot(self):
        self.run_probe("screenshot")

    def test_startup_does_not_add_capture_or_change_environment(self):
        self.run_probe("startup")

    def test_other_keybindings_layout_and_device_settings_are_preserved(self):
        self.run_probe("desktop")

    def test_dictation_toggle_uses_a_single_non_conflicting_shortcut(self):
        self.run_probe("dictation")

    def test_login_imports_session_before_starting_managed_voxtype(self):
        result = subprocess.run(
            ["lua", str(PROBE), str(CONFIG), "voxtype_startup"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        command = result.stdout.strip()
        # Reject absolute systemctl paths; PATH below contains only the fake.
        self.assertNotIn("/systemctl", command)
        with tempfile.TemporaryDirectory(prefix="hypr-voxtype-") as temp:
            bin_dir = Path(temp)
            (bin_dir / "sh").symlink_to("/bin/sh")
            fake = bin_dir / "systemctl"
            fake.write_text(
                "#!/bin/sh\n"
                'printf "%s\\n" "$*" >> "$CALLS"\n'
                'if [ "$FAIL_IMPORT" = 1 ] && [ "$2" = import-environment ]; then exit 23; fi\n'
            )
            fake.chmod(0o755)
            calls = bin_dir / "calls"
            env = {
                "PATH": str(bin_dir), "CALLS": str(calls), "FAIL_IMPORT": "0",
                "WAYLAND_DISPLAY": "wayland-fixture", "DISPLAY": ":17",
                "XDG_CURRENT_DESKTOP": "Hyprland", "XDG_SESSION_TYPE": "wayland",
                "HYPRLAND_INSTANCE_SIGNATURE": "fixture-signature",
            }
            for _ in range(2):
                started = subprocess.run(
                    ["/bin/sh", "-c", command], env=env,
                    capture_output=True, text=True, check=False, timeout=5,
                )
                self.assertEqual(started.returncode, 0, started.stderr)
            self.assertEqual(calls.read_text().splitlines(), [
                "--user import-environment WAYLAND_DISPLAY DISPLAY XDG_CURRENT_DESKTOP XDG_SESSION_TYPE HYPRLAND_INSTANCE_SIGNATURE",
                "--user start voxtype.service",
            ] * 2)

            calls.write_text("")
            env["FAIL_IMPORT"] = "1"
            failed = subprocess.run(
                ["/bin/sh", "-c", command], env=env,
                capture_output=True, text=True, check=False, timeout=5,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(calls.read_text().splitlines(), [
                "--user import-environment WAYLAND_DISPLAY DISPLAY XDG_CURRENT_DESKTOP XDG_SESSION_TYPE HYPRLAND_INSTANCE_SIGNATURE",
            ])


if __name__ == "__main__":
    unittest.main()
