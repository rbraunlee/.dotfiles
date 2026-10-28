"""Install the real package into disposable homes without downloading plugins."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


PACKAGE = Path(__file__).resolve().parents[3] / "common/tmux"


class StowLifecycle(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="tmux-stow-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.packages = self.root / "packages"
        self.package = self.packages / "tmux"
        shutil.copytree(PACKAGE, self.package)
        legacy = self.package / ".config/tmux/plugins/old-plugin"
        legacy.mkdir(parents=True, exist_ok=True)
        (legacy / "keep").write_text("legacy data")

    def stow(self, *options):
        return subprocess.run(
            ["stow", *options, "--no-folding", "-t", str(self.home),
             "-d", str(self.packages), "tmux"],
            text=True, capture_output=True, timeout=10,
        )

    def test_install_restow_unstow_preserves_plugin_data(self):
        plugin = self.home / ".tmux/plugins/tpm/local-data"
        plugin.parent.mkdir(parents=True)
        plugin.write_text("runtime data")
        config = self.home / ".config/tmux/tmux.conf"
        for options in [(), ("-R",)]:
            result = self.stow(*options)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(config.is_symlink())
            self.assertEqual(config.resolve(), self.package / ".config/tmux/tmux.conf")
            self.assertFalse((self.home / ".config/tmux/plugins").exists())
            self.assertFalse((self.home / "README.md").exists())
            self.assertFalse((self.home / ".gitignore").exists())
            self.assertEqual(plugin.read_text(), "runtime data")
        result = self.stow("-D")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(config.exists())
        self.assertEqual(plugin.read_text(), "runtime data")
        self.assertEqual((self.package / ".config/tmux/plugins/old-plugin/keep").read_text(),
                         "legacy data")

    def test_existing_config_conflicts_without_overwrite(self):
        config = self.home / ".config/tmux/tmux.conf"
        config.parent.mkdir(parents=True)
        config.write_text("existing configuration")
        for options in [("-n",), ()]:
            result = self.stow(*options)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(config.is_symlink())
            self.assertEqual(config.read_text(), "existing configuration")


if __name__ == "__main__":
    unittest.main()
