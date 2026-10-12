"""Contract checks for the Wofi stylesheet (not graphical interaction)."""

import pathlib
import re
import subprocess
import tempfile
import unittest


STYLE = pathlib.Path(__file__).resolve().parents[3] / "linux/wofi/.config/wofi/style.css"
CONFIG = STYLE.with_name("config")
PROBE = pathlib.Path(__file__).with_name("gtk_css_probe.c")


def css_rules(text):
    """Return the explicitly declared selectors and declarations in this small stylesheet."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return [(selector.strip(), dict(re.findall(r"([\w-]+)\s*:\s*([^;]+);", body)))
            for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", text)]


class SelectionContractTests(unittest.TestCase):
    def test_selected_entry_not_focused_entry_has_blue_highlight(self):
        rules = css_rules(STYLE.read_text())
        selected = [declarations for selector, declarations in rules
                    if selector == "#entry:selected"]
        self.assertEqual(selected, [{"background-color": "#458588", "color": "#ebdbb2",
                                     "border": "none", "outline": "none"}])
        self.assertNotIn("#entry:focus", [selector for selector, _ in rules])
        self.assertLess([selector for selector, _ in rules].index("#entry:nth-child(even)"),
                        [selector for selector, _ in rules].index("#entry:selected"))

    def test_unnamed_secondary_action_list_has_no_id_rule(self):
        self.assertNotIn("#list", [selector for selector, _ in css_rules(STYLE.read_text())])


class PreservationTests(unittest.TestCase):
    def test_launcher_configuration_is_unchanged(self):
        self.assertEqual(CONFIG.read_text(), """width=600
height=300
location=center
show=drun
prompt=Search...
filter_rate=100
allow_markup=true
no_actions=true
halign=fill
orientation=vertical
content_halign=fill
insensitive=true
allow_images=true
image_size=20
gtk_dark=true
dynamic_lines=true
""")

    def test_other_rules_and_entry_geometry_retain_original_declarations(self):
        self.assertEqual(css_rules(STYLE.read_text()), [
            ("window", {"background-color": "#282828", "border": "2px solid #a89984",
                        "border-radius": "8px", "font-family": '"monospace"',
                        "color": "#ebdbb2", "padding": "10px", "margin": "10px"}),
            ("#outer-box", {"margin": "5px", "padding": "5px"}),
            ("#inner-box", {"margin": "5px", "padding": "5px"}),
            ("#input", {"background-color": "#3c3836", "color": "#ebdbb2",
                        "border": "none", "border-radius": "5px", "padding": "8px 12px",
                        "margin-bottom": "10px", "font-size": "14px"}),
            ("#scroll", {"margin-top": "10px"}),
            ("#entry", {"background-color": "transparent", "padding": "8px 12px",
                        "border-radius": "5px", "margin": "2px 0"}),
            ("#entry:nth-child(even)", {"background-color": "#2e2c2b"}),
            ("#entry:selected", {"background-color": "#458588", "color": "#ebdbb2",
                                 "border": "none", "outline": "none"}),
            ("#img", {"margin-right": "10px", "font-size": "20px"}),
            ("#text", {"font-size": "14px"}),
        ])


class NativeSyntaxTests(unittest.TestCase):
    def test_stylesheet_loads_in_gtk3_provider_without_parsing_errors(self):
        flags = subprocess.check_output(["pkg-config", "--cflags", "--libs", "gtk+-3.0"],
                                        text=True).split()
        with tempfile.TemporaryDirectory(prefix="wofi-gtk-", dir="/tmp/opencode") as root:
            binary = pathlib.Path(root) / "probe"
            subprocess.run(["cc", str(PROBE), "-o", str(binary), *flags], check=True,
                           capture_output=True, text=True)
            result = subprocess.run([str(binary), str(STYLE)], capture_output=True, text=True,
                                    env={"GDK_BACKEND": "none"})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
