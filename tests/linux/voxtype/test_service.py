"""Check the user-service boundary without starting a daemon."""

import configparser
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[3]
UNIT = ROOT / "linux/voxtype/.config/systemd/user/voxtype.service"
HYPRLAND = ROOT / "linux/hypr/.config/hypr/hyprland.lua"


class UserServiceTests(unittest.TestCase):
    def test_graphical_session_starts_one_wtype_only_daemon(self):
        unit = configparser.ConfigParser(interpolation=None, strict=True)
        self.assertTrue(unit.read(UNIT), "Stow must provide a Voxtype user unit")

        self.assertEqual(unit["Service"]["Type"], "simple")
        self.assertEqual(unit["Service"]["ExecStart"], "/usr/bin/voxtype -q daemon")
        self.assertEqual(unit["Service"]["Restart"], "on-failure")
        self.assertEqual(unit["Install"]["WantedBy"], "graphical-session.target")
        self.assertEqual(unit["Unit"]["PartOf"], "graphical-session.target")
        self.assertNotIn("ydotool", UNIT.read_text().lower())
        self.assertNotIn("input' group", UNIT.read_text().lower())
        self.assertIsNone(re.search(r"voxtype\s+(?:-q\s+)?daemon\b", HYPRLAND.read_text()))
