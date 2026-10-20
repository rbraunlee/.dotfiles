"""Check the installed-release config boundary without recording audio."""

from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "linux/voxtype"
CONFIG = PACKAGE / ".config/voxtype/config.toml"
SERVICE = PACKAGE / ".config/systemd/user/voxtype.service"


class DictationConfigTests(unittest.TestCase):
    def test_local_english_typing_preserves_manual_submission(self):
        with CONFIG.open("rb") as file:
            config = tomllib.load(file)

        self.assertEqual(config["engine"], "whisper")
        self.assertEqual(config["state_file"], "auto")
        self.assertFalse(config["hotkey"]["enabled"])
        self.assertEqual(config["whisper"]["mode"], "local")
        self.assertEqual(config["whisper"]["model"], "large-v3-turbo")
        self.assertEqual(config["whisper"]["language"], "en")
        self.assertNotIn("remote_endpoint", config["whisper"])
        self.assertEqual(config["output"]["mode"], "type")
        self.assertEqual(config["output"]["driver_order"], ["wtype"])
        self.assertFalse(config["output"]["fallback_to_clipboard"])
        self.assertFalse(config["output"]["auto_submit"])
        self.assertTrue(config["output"]["shift_enter_newlines"])
        self.assertFalse(config["text"]["smart_auto_submit"])
        self.assertNotIn("post_process", config["output"])
        self.assertTrue(config["output"]["notification"]["on_recording_start"])
        self.assertTrue(config["output"]["notification"]["on_recording_stop"])

    def test_stow_links_package_without_touching_real_home_or_adopting_conflicts(self):
        with tempfile.TemporaryDirectory(prefix="voxtype-stow-") as home:
            target = Path(home) / ".config/voxtype/config.toml"
            result = subprocess.run(
                ["stow", "-d", str(ROOT / "linux"), "-t", home, "voxtype"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.resolve(), CONFIG)

        with tempfile.TemporaryDirectory(prefix="voxtype-conflict-") as home:
            target = Path(home) / ".config/voxtype/config.toml"
            target.parent.mkdir(parents=True)
            target.write_text("owner config\n")
            result = subprocess.run(
                ["stow", "-d", str(ROOT / "linux"), "-t", home, "voxtype"],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_text(), "owner config\n")

    def test_stow_links_config_and_service_and_refuses_existing_service(self):
        with tempfile.TemporaryDirectory(prefix="voxtype-unit-stow-") as home:
            config = Path(home) / ".config/voxtype/config.toml"
            unit = Path(home) / ".config/systemd/user/voxtype.service"
            config.parent.mkdir(parents=True)
            unit.parent.mkdir(parents=True)
            result = subprocess.run(
                ["stow", "-d", str(ROOT / "linux"), "-t", home, "voxtype"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(config.is_symlink())
            self.assertEqual(config.resolve(), CONFIG)
            self.assertTrue(unit.is_symlink())
            self.assertEqual(unit.resolve(), SERVICE)

        with tempfile.TemporaryDirectory(prefix="voxtype-unit-conflict-") as home:
            unit = Path(home) / ".config/systemd/user/voxtype.service"
            unit.parent.mkdir(parents=True)
            unit.write_text("owner service\n")
            result = subprocess.run(
                ["stow", "-d", str(ROOT / "linux"), "-t", home, "voxtype"],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(unit.read_text(), "owner service\n")
            self.assertFalse(unit.is_symlink())
