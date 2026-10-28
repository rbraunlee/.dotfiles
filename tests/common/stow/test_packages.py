"""Check repository package layout without touching the real home or services."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
TARGETS = {
    'common/agent-skills': '.agents/skills/implement/SKILL.md',
    'common/claude': '.claude/settings.json',
    'common/codex': '.codex/config.toml',
    'common/cursor': '.cursor/skills/brainstorm/SKILL.md',
    'common/ghostty': '.config/ghostty/config.ghostty',
    'common/nvim': '.config/nvim/init.lua',
    'common/opencode': '.config/opencode/opencode.jsonc',
    'common/starship': '.config/starship.toml',
    'common/tmux': '.config/tmux/tmux.conf',
    'common/wallpaper': 'Pictures/Wallpapers/gruvbox_arch.png',
    'common/zsh': '.zshrc',
    'linux/bash': '.bashrc',
    'linux/hypr': '.config/hypr/hyprland.lua',
    'linux/swappy': '.config/swappy/config',
    'linux/voxtype': '.config/voxtype/config.toml',
    'linux/waybar': '.config/waybar/config.jsonc',
    'linux/wofi': '.config/wofi/config',
    'linux/zsh': '.zprofile',
    'macos/aerospace': '.config/aerospace/aerospace.toml',
}


class PackageInstallation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='dotfiles-stow-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.base = Path(cls.temporary.name)
        cls.checkout = cls.base / 'checkout'
        # Include working edits/new files, but exclude runtime dependencies and
        # ignored experimental residue. Preserve relative cross-package links.
        paths = subprocess.check_output(
            ['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard',
             '--', 'common', 'linux', 'macos'], cwd=ROOT,
        ).decode().split('\0')
        for relative in filter(None, paths):
            source = ROOT / relative
            if not source.is_file() and not source.is_symlink():
                continue
            target = cls.checkout / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target, follow_symlinks=False)
        packages = {str(p.relative_to(cls.checkout))
                    for group in ('common', 'linux', 'macos')
                    for p in (cls.checkout / group).iterdir() if p.is_dir()}
        if packages != TARGETS.keys():
            raise AssertionError(f'Update package coverage: {packages ^ TARGETS.keys()}')

    def stow(self, home, package, *options):
        group, name = package.split('/')
        return subprocess.run(
            ['stow', *options, '--no-folding', '-d', str(self.checkout / group),
             '-t', str(home), name], capture_output=True, text=True, timeout=15,
        )

    def assert_installed(self, home, packages):
        for package in packages:
            target = home / TARGETS[package]
            self.assertTrue(target.is_symlink(), str(target))
            self.assertEqual(target.resolve(),
                             (self.checkout / package / TARGETS[package]).resolve())
        for path in home.rglob('*'):
            if path.is_symlink():
                self.assertTrue(path.exists(), f'Broken installed link: {path}')
        self.assertFalse((home / 'README.md').exists())

    def test_each_package_install_restow_unstow(self):
        for package in TARGETS:
            with self.subTest(package=package), tempfile.TemporaryDirectory(dir=self.base) as tmp:
                home = Path(tmp)
                for options in [(), ('-R',)]:
                    result = self.stow(home, package, *options)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assert_installed(home, [package])
                result = self.stow(home, package, '-D')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((home / TARGETS[package]).is_symlink())

    def test_each_package_refuses_existing_config(self):
        for package, relative in TARGETS.items():
            with self.subTest(package=package), tempfile.TemporaryDirectory(dir=self.base) as tmp:
                home = Path(tmp)
                target = home / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('preserve existing file')
                result = self.stow(home, package)
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertEqual(target.read_text(), 'preserve existing file')
                self.assertFalse(target.is_symlink())

    def test_platform_combinations_preserve_runtime_files(self):
        for platform in ('linux', 'macos'):
            packages = [p for p in TARGETS if p.startswith(('common/', platform + '/'))]
            with self.subTest(platform=platform), tempfile.TemporaryDirectory(dir=self.base) as tmp:
                home = Path(tmp)
                for package in packages:
                    result = self.stow(home, package)
                    self.assertEqual(result.returncode, 0, result.stderr)
                self.assert_installed(home, packages)
                runtime = [home / name for name in (
                    '.claude/sessions/keep', '.codex/sessions/keep',
                    '.cursor/local-state/keep', '.config/opencode/node_modules/keep',
                    '.tmux/plugins/local/keep')]
                for path in runtime:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('runtime state')
                    self.assertTrue(path.resolve().is_relative_to(home))
                for package in packages:
                    result = self.stow(home, package, '-R')
                    self.assertEqual(result.returncode, 0, result.stderr)
                self.assert_installed(home, packages)
                for package in reversed(packages):
                    result = self.stow(home, package, '-D')
                    self.assertEqual(result.returncode, 0, result.stderr)
                for path in runtime:
                    self.assertEqual(path.read_text(), 'runtime state')
                self.assertFalse(any(p.is_symlink() for p in home.rglob('*')))


if __name__ == '__main__':
    unittest.main()
