"""Offline lockfile integrity and installer failure-order checks."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
PACKAGES = (
    ROOT / 'common/opencode/.config/opencode',
    ROOT / 'common/codex/.local/share/codex-mcp',
    ROOT / 'common/claude/.claude/mcp',
)


class Dependencies(unittest.TestCase):
    def test_locks_match_manifests_and_pin_registry_artifacts(self):
        for package in PACKAGES:
            with self.subTest(package=package):
                manifest = json.loads((package / 'package.json').read_text())
                lock = json.loads((package / 'package-lock.json').read_text())
                self.assertTrue(manifest['private'])
                self.assertEqual(lock['lockfileVersion'], 3)
                self.assertEqual(lock['name'], manifest['name'])
                self.assertEqual(lock['packages']['']['dependencies'], manifest['dependencies'])
                for name, version in manifest['dependencies'].items():
                    self.assertEqual(lock['packages']['node_modules/' + name]['version'], version)
                for name, entry in lock['packages'].items():
                    if not name:
                        continue
                    self.assertTrue(entry['version'], name)
                    self.assertTrue(entry['resolved'].startswith('https://registry.npmjs.org/'), name)
                    self.assertTrue(entry['integrity'].startswith('sha512-'), name)

    def installer(self, npm_status):
        with tempfile.TemporaryDirectory(prefix='mcp-installer-') as tmp:
            root = Path(tmp)
            log = root / 'calls'
            for name, body in {
                'npm': 'printf "npm:%s\\n" "$*" >> "$CALL_LOG"\nexit "$NPM_STATUS"\n',
                'claude': 'printf "claude:%s\\n" "$*" >> "$CALL_LOG"\n',
            }.items():
                command = root / name
                command.write_text('#!/bin/sh\n' + body)
                command.chmod(0o755)
            result = subprocess.run(
                ['/bin/sh', str(PACKAGES[2] / 'install.sh')],
                env={**os.environ, 'HOME': str(root), 'PATH': str(root) + os.pathsep + os.defpath,
                     'CALL_LOG': str(log), 'NPM_STATUS': str(npm_status)},
                capture_output=True, text=True, timeout=10,
            )
            return result, log.read_text().splitlines()

    def test_successful_install_precedes_registration(self):
        result, calls = self.installer(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(calls[0].startswith('npm:ci --prefix '), calls)
        self.assertEqual(sum(line.startswith('claude:mcp add-json') for line in calls), 3)

    def test_failed_install_does_not_change_registrations(self):
        result, calls = self.installer(7)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith('npm:ci --prefix '))


if __name__ == '__main__':
    unittest.main()
