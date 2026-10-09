"""Native tmux configuration checks; no TPM, existing server, or saved sessions."""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


CONFIG = Path(__file__).resolve().parents[3] / "common/tmux/.config/tmux/tmux.conf"
TPM_BOOTSTRAP = "run '~/.tmux/plugins/tpm/tpm'"


class NativeTmuxConfig(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory(prefix="tmux-native-")
        self.addCleanup(self.root.cleanup)
        root = Path(self.root.name)
        self.socket = root / "socket"
        self.env = os.environ.copy()
        self.env.pop("TMUX", None)
        self.env["HOME"] = str(root)
        self.env["ZDOTDIR"] = str(root)
        self.env["XDG_CONFIG_HOME"] = str(root / "config")
        self.env["XDG_DATA_HOME"] = str(root / "data")
        lines = CONFIG.read_text().splitlines()
        self.assertEqual(lines.count(TPM_BOOTSTRAP), 1, "expected one TPM bootstrap")
        self.assertFalse(
            any(re.match(r"\s*(?:run|run-shell)\b", line) and line != TPM_BOOTSTRAP
                for line in lines),
            "unexpected external command in the fixture",
        )
        config = root / "tmux.conf"
        config.write_text("\n".join(line for line in lines if line != TPM_BOOTSTRAP) + "\n")
        self.run_tmux("-f", str(config), "new-session", "-d", "-s", "native", "/bin/sleep 30")
        self.addCleanup(self.stop_server)

    def run_tmux(self, *args, check=True):
        return subprocess.run(
            ["tmux", "-S", str(self.socket), *args],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=5,
            check=check,
        )

    def stop_server(self):
        self.run_tmux("kill-server", check=False)

    def option(self, name):
        return self.run_tmux("show-options", "-gqv", name).stdout.strip()

    def test_xterm_true_color_override_has_native_capability_separator(self):
        overrides = self.option("terminal-overrides").splitlines()
        self.assertIn("xterm*:Tc", overrides)
        self.assertNotIn("xterm*Tc", overrides)

    def test_vi_copy_y_uses_native_copy_and_cancel(self):
        bindings = self.run_tmux("list-keys", "-T", "copy-mode-vi").stdout
        self.assertIsNotNone(re.search(
            r"^bind-key\s+-T copy-mode-vi y\s+send-keys -X copy-selection-and-cancel$",
            bindings, re.MULTILINE,
        ))

    def test_process_restoration_uses_conservative_plugin_defaults(self):
        self.assertEqual(
            self.run_tmux("show-options", "-gq", "@resurrect-processes").stdout,
            "",
        )

    def test_existing_persistence_and_session_preferences_remain_effective(self):
        for name, expected in {
            "@continuum-restore": "on",
            "@resurrect-capture-pane-contents": "on",
            "@continuum-save-interval": "5",
            "mouse": "on",
            "base-index": "1",
            "pane-base-index": "1",
            "renumber-window": "on",
            "@tmux-gruvbox": "dark",
            "prefix": "C-b",
        }.items():
            with self.subTest(option=name):
                self.assertEqual(self.option(name), expected)
        self.assertEqual(
            self.run_tmux("show-options", "-gwqv", "mode-keys").stdout.strip(),
            "vi",
        )

    def test_existing_navigation_and_selection_bindings_remain_effective(self):
        root_bindings = self.run_tmux("list-keys", "-T", "root").stdout
        vi_bindings = self.run_tmux("list-keys", "-T", "copy-mode-vi").stdout
        for bindings, pattern in (
            (root_bindings, r"^bind-key\s+-T root M-H\s+previous-window$"),
            (root_bindings, r"^bind-key\s+-T root M-L\s+next-window$"),
            (vi_bindings, r"^bind-key\s+-T copy-mode-vi v\s+send-keys -X begin-selection$"),
            (vi_bindings, r"^bind-key\s+-T copy-mode-vi C-v\s+send-keys -X rectangle-toggle$"),
        ):
            with self.subTest(binding=pattern):
                self.assertIsNotNone(re.search(pattern, bindings, re.MULTILINE))

    def test_plugin_declarations_and_loader_remain_in_package(self):
        lines = CONFIG.read_text().splitlines()
        self.assertEqual(
            [line for line in lines if line.startswith("set -g @plugin ")],
            [
                "set -g @plugin 'egel/tmux-gruvbox'",
                "set -g @plugin 'tmux-plugins/tpm'",
                "set -g @plugin 'tmux-plugins/tmux-sensible'",
                "set -g @plugin 'christoomey/vim-tmux-navigator'",
                "set -g @plugin 'tmux-plugins/tmux-yank'",
                "set -g @plugin 'tmux-plugins/tmux-resurrect'",
                "set -g @plugin 'tmux-plugins/tmux-continuum'",
            ],
        )
        self.assertIn(TPM_BOOTSTRAP, lines)
        self.assertIn("# set -g prefix C-Space", lines)


if __name__ == "__main__":
    unittest.main()
