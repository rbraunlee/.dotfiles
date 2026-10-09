"""Invoke public Zsh shortcuts with only disposable fake command providers."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ZSHRC = Path(__file__).resolve().parents[3] / "common/zsh/.zshrc"


class DailyHelpersTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="zsh-daily-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.fixture = self.root / "functions"
        self.fixture.mkdir()
        (self.fixture / "compinit").write_text(":\n")
        self.trace = self.root / "calls"
        self.provider("tty", '#!/bin/sh\necho /dev/fixture-tty\n')

    def provider(self, name, code=None):
        # No fake invokes a real provider; even pipeline input is handled here.
        if code is None:
            code = '''#!/usr/bin/python3
import json, os, sys
with open(os.environ["CALLS"], "a") as output:
    output.write(json.dumps([os.path.basename(sys.argv[0]), sys.argv[1:]]) + "\\n")
if os.environ.get("INPUT_PROVIDER") == os.path.basename(sys.argv[0]):
    print(os.environ.get("INPUT_TEXT", ""))
sys.exit(int(os.environ.get("FAIL_" + os.path.basename(sys.argv[0]), "0")))
'''
        path = self.bin / name
        path.write_text(code)
        path.chmod(0o755)

    def run_shell(self, invocation, *, ostype="linux-gnu", extra_env=None):
        commands = self.root / "commands.zsh"
        commands.write_text(invocation + "\n")
        env = {
            "HOME": str(self.home), "ZDOTDIR": str(self.root),
            "XDG_DATA_HOME": str(self.root / "xdg"),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_CACHE_HOME": str(self.root / "cache"),
            "CUDA_HOME": str(self.root / "absent-cuda"),
            "PATH": str(self.bin), "ZSHRC": str(ZSHRC),
            "FIXTURE": str(self.fixture), "CALLS": str(self.trace), "BIN": str(self.bin),
            "COMMANDS": str(commands),
        }
        env.update(extra_env or {})
        # The macOS branch prepends legacy paths. Restore the fixture-only PATH
        # before any test invocation so no live provider can be resolved there.
        script = (f'OSTYPE={ostype}\nfpath=( "$FIXTURE" )\nsource "$ZSHRC"\n'
                  'path=( "$BIN" )\nsource "$COMMANDS"\n')
        result = subprocess.run(["/usr/bin/zsh", "-f", "-c", script], env=env,
                                cwd=self.root, capture_output=True, text=True, timeout=10)
        calls = [json.loads(line) for line in self.trace.read_text().splitlines()] if self.trace.exists() else []
        return result, calls

    def test_daily_listing_and_linux_inspection_forward_expected_arguments(self):
        for name in ("ls", "df", "free", "ps", "journalctl", "systemctl", "pactl", "grep"):
            self.provider(name)
        result, calls = self.run_shell("la; ll; df; free; psa; psgrep 'a ; $(touch escape) * -n'; jctl; sysfailed; audio")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertCountEqual(calls, [
            ["ls", ["-a"]], ["ls", ["-alFh"]], ["df", ["-h"]],
            ["free", ["-mt"]], ["ps", ["auxf"]], ["ps", ["aux"]],
            ["grep", ["-i", "-F", "-e", "VSZ", "-e", "a ; $(touch escape) * -n"]],
            ["journalctl", ["-p", "3", "-xb"]],
            ["systemctl", ["list-units", "--failed"]],
            ["pactl", ["info"]], ["grep", ["-F", "Server Name"]],
        ])
        self.assertFalse((self.root / "escape").exists())

    def test_mac_has_portable_listing_but_no_linux_shortcuts(self):
        self.provider("ls")
        result, calls = self.run_shell('la; ll; for name in free psa psgrep jctl sysfailed audio; do '
                                       '(( $+aliases[$name] || $+functions[$name] )) && exit 32; done; true',
                                       ostype="darwin24")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [["ls", ["-a"]], ["ls", ["-alFh"]]])

    def test_process_and_audio_require_arguments_and_providers_and_report_failures(self):
        for invocation, message in (("psgrep", "one process name"),
                                    ("psgrep a b", "one process name"),
                                    ("psgrep ''", "one process name"),
                                    ("psgrep 'literal name'", "ps and grep"),
                                    ("audio", "pactl and grep")):
            with self.subTest(invocation=invocation):
                result, calls = self.run_shell(invocation)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertEqual(calls, [])

        for name in ("ps", "grep", "pactl"):
            self.provider(name)
        for invocation, failed, expected in (
            ("psgrep 'literal name'", "FAIL_ps", [["ps", ["aux"]],
                                                   ["grep", ["-i", "-F", "-e", "VSZ", "-e", "literal name"]]]),
            ("audio", "FAIL_pactl", [["pactl", ["info"]],
                                      ["grep", ["-F", "Server Name"]]]),
        ):
            with self.subTest(invocation=invocation):
                result, calls = self.run_shell(invocation, extra_env={failed: "23"})
                self.assertNotEqual(result.returncode, 0)
                self.assertCountEqual(calls, expected)
                self.trace.unlink()

    def test_ex_forwards_one_literal_archive_to_each_format_provider(self):
        for tool in ("tar", "bunzip2", "unrar", "gunzip", "unzip", "uncompress", "7z", "ar"):
            self.provider(tool)
        cases = {
            "tar.bz2": ("tar", ["xjf"]), "tar.gz": ("tar", ["xzf"]),
            "bz2": ("bunzip2", []), "rar": ("unrar", ["x"]),
            "gz": ("gunzip", []), "tar": ("tar", ["xf"]),
            "tbz2": ("tar", ["xjf"]), "tgz": ("tar", ["xzf"]),
            "zip": ("unzip", []), "Z": ("uncompress", []),
            "7z": ("7z", ["x"]), "deb": ("ar", ["x"]),
            "tar.xz": ("tar", ["xf"]), "tar.zst": ("tar", ["xf"]),
        }
        for suffix, (tool, flags) in cases.items():
            with self.subTest(suffix=suffix):
                filename = f"-literal ; $(touch escape) [*].{suffix}"
                (self.root / filename).write_bytes(b"fixture only: never extracted")
                result, calls = self.run_shell('ex "$ARCHIVE"', extra_env={"ARCHIVE": filename})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [[tool, flags + ["./" + filename]]])
                self.assertFalse((self.root / "escape").exists())
                self.trace.unlink()

    def test_ex_rejects_bad_input_without_invoking_any_provider(self):
        for invocation, reason in (
            ("ex", "one"), ("ex a b", "one"), ("ex absent.zip", "existing"),
            ('ex "$ARCHIVE"', "unsupported"),
        ):
            with self.subTest(invocation=invocation):
                (self.root / "unknown.xyz").write_bytes(b"fixture")
                result, calls = self.run_shell(invocation, extra_env={"ARCHIVE": "unknown.xyz"})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stderr)
                self.assertEqual(calls, [])

    def test_ex_missing_provider_and_failed_extraction_report_nonzero(self):
        (self.root / "safe.zip").write_bytes(b"fixture")
        result, calls = self.run_shell('ex safe.zip')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unzip", result.stderr)
        self.assertEqual(calls, [])
        self.provider("unzip")
        result, calls = self.run_shell('ex safe.zip', extra_env={"FAIL_unzip": "17"})
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertIn("failed", result.stderr)
        self.assertEqual(calls, [["unzip", ["safe.zip"]]])

    def test_ex_preserves_absolute_and_relative_names_with_spaces(self):
        self.provider("unzip")
        for filename in ("space [*] ; name.zip", str(self.root / "absolute [*] ; name.zip")):
            with self.subTest(filename=filename):
                (self.root / Path(filename).name).write_bytes(b"fixture only")
                result, calls = self.run_shell('ex "$ARCHIVE"', extra_env={"ARCHIVE": filename})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [["unzip", [filename]]])
                self.trace.unlink()

    def test_source_does_not_call_daily_or_archive_providers(self):
        for name in ("ps", "grep", "pactl", "unzip", "journalctl", "systemctl"):
            self.provider(name)
        result, calls = self.run_shell('source "$ZSHRC"; true')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
