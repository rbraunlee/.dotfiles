"""Exercise the real Hyprland Lua config against a no-desktop API double."""

from pathlib import Path
import subprocess
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


if __name__ == "__main__":
    unittest.main()
