"""Regression checks for the deployed Waybar configuration (no live bar needed)."""

import json
import re
import unittest
from pathlib import Path


CONFIG = Path(__file__).resolve().parents[3] / "linux/waybar/.config/waybar/config.jsonc"


def rendered_config():
    text = CONFIG.read_text(encoding="utf-8")
    # JSONC comments and trailing commas are accepted by Waybar, but not by json.
    quoted_or_comment = re.compile(r'("(?:\\.|[^"\\])*")|//[^\n]*|/\*.*?\*/', re.DOTALL)
    text = quoted_or_comment.sub(lambda match: match.group(1) or "", text)
    quoted_or_trailing_comma = re.compile(r'("(?:\\.|[^"\\])*")|,(?=\s*[}\]])')
    text = quoted_or_trailing_comma.sub(lambda match: match.group(1) or "", text)
    return json.loads(text)


class NetworkPresentationTests(unittest.TestCase):
    def test_wifi_uses_supported_format_and_preserves_other_network_states(self):
        self.assertEqual(
            rendered_config()["network"],
            {
                "format-wifi": " {essid}",
                "format-ethernet": "󰈀 {ifname}",
                "format-disconnected": "󰤮 Disconnected",
                "tooltip": True,
            },
        )

    def test_network_remains_in_existing_bar_layout(self):
        config = rendered_config()
        self.assertEqual(config["modules-left"], ["hyprland/workspaces"])
        self.assertEqual(config["modules-center"], ["hyprland/window"])
        self.assertEqual(
            config["modules-right"],
            [
                "tray", "custom/updates", "wireplumber", "backlight",
                "network", "battery", "clock", "custom/lock_screen",
                "custom/power_btn",
            ],
        )


if __name__ == "__main__":
    unittest.main()
