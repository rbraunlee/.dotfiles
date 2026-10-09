"""Native Zsh package shortcuts against disposable, non-delegating providers."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ZSHRC = Path(__file__).resolve().parents[3] / "common/zsh/.zshrc"


class ArchPackagesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="zsh-arch-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.fixture = self.root / "functions"
        self.fixture.mkdir()
        (self.fixture / "compinit").write_text(":\n")
        self.calls = self.root / "calls"
        self.provider("tty", '#!/bin/sh\necho /dev/fixture-tty\n')

    def provider(self, name, code=None):
        if code is None:
            # Never dispatch any recorded argv: in particular fake sudo cannot
            # execute pacman, and fake pacman cannot reach repositories.
            code = '''#!/usr/bin/python3
import json, os, sys
name = os.path.basename(sys.argv[0])
with open(os.environ["CALLS"], "a") as output:
    output.write(json.dumps([name, sys.argv[1:]]) + "\\n")
print(os.environ.get("OUTPUT_" + name, ""), end="")
sys.exit(int(os.environ.get("FAIL_" + name, "0")))
'''
        target = self.bin / name
        target.write_text(code)
        target.chmod(0o755)

    def run_shell(self, invocation, *, ostype="linux-gnu", extra_env=None):
        env = {
            "HOME": str(self.home), "ZDOTDIR": str(self.root),
            "XDG_DATA_HOME": str(self.root / "xdg"),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_CACHE_HOME": str(self.root / "cache"),
            "CUDA_HOME": str(self.root / "absent-cuda"),
            "PATH": str(self.bin), "BIN": str(self.bin),
            "ZSHRC": str(ZSHRC), "FIXTURE": str(self.fixture),
            "CALLS": str(self.calls),
        }
        env.update(extra_env or {})
        # Only the absolute Zsh executable, builtins and fixture PATH are used.
        # The macOS startup branch may add legacy paths: restore PATH before use.
        script = (f'OSTYPE={ostype}\nfpath=( "$FIXTURE" )\nsource "$ZSHRC"\n'
                  'path=( "$BIN" )\n' + invocation + "\n")
        result = subprocess.run(["/usr/bin/zsh", "-f", "-c", script], env=env,
                                cwd=self.root, capture_output=True, text=True, timeout=10)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        return result, calls

    def test_install_and_remove_pass_literal_packages_without_bypassing_confirmation(self):
        self.provider("pacman")
        self.provider("sudo")
        name = 'literal ; $(touch escape) * -n'
        result, calls = self.run_shell('sps "$PACKAGE"; spr "$PACKAGE"; sprs "$PACKAGE"',
                                       extra_env={"PACKAGE": name})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [["sudo", ["pacman", "-S", name]],
                                 ["sudo", ["pacman", "-R", name]],
                                 ["sudo", ["pacman", "-Rs", name]]])
        self.assertFalse((self.root / "escape").exists())

    def test_queries_and_dependency_inspection_never_request_sudo(self):
        self.provider("pacman")
        self.provider("sudo")
        result, calls = self.run_shell('spqo "$PACKAGE"; spsii "$PACKAGE"; depends "$PACKAGE"; '
                                       'list; listt; listaur', extra_env={"PACKAGE": "a b*;"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [["pacman", ["-Qo", "--", "a b*;"]],
                                 ["pacman", ["-Sii", "--", "a b*;"]],
                                 ["pacman", ["-Sii", "--", "a b*;"]],
                                 ["pacman", ["-Qqe"]], ["pacman", ["-Qqet"]],
                                 ["pacman", ["-Qqem"]]])

    def test_option_looking_query_target_is_not_interpreted_as_a_pacman_switch(self):
        self.provider('pacman')
        result, calls = self.run_shell('spqo -n; spsii --noconfirm; depends --noconfirm')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [['pacman', ['-Qo', '--', '-n']],
                                 ['pacman', ['-Sii', '--', '--noconfirm']],
                                 ['pacman', ['-Sii', '--', '--noconfirm']]])

    def test_upgrades_use_normal_refresh_and_never_suppress_confirmation(self):
        for name in ("sudo", "pacman", "paru"):
            self.provider(name)
        result, calls = self.run_shell('update; upd; upall; upa')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [["sudo", ["pacman", "-Syu"]],
                                 ["sudo", ["pacman", "-Syu"]],
                                 ["paru", ["-Syu"]], ["paru", ["-Syu"]]])

    def test_failed_upgrade_provider_cannot_fall_through_to_another_mutation(self):
        for name in ("sudo", "pacman", "paru"):
            self.provider(name)
        result, calls = self.run_shell('update', extra_env={"FAIL_sudo": "23"})
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(calls, [["sudo", ["pacman", "-Syu"]]])
        self.calls.unlink()
        result, calls = self.run_shell('upall', extra_env={"FAIL_paru": "18"})
        self.assertEqual(result.returncode, 18, result.stderr)
        self.assertEqual(calls, [["paru", ["-Syu"]]])

    def test_cleanup_skips_empty_orphans_and_removes_nonempty_list_with_confirmation(self):
        self.provider("pacman")
        self.provider("sudo")
        for status in ("0", "1"):
            with self.subTest(status=status):
                result, calls = self.run_shell('cleanup', extra_env={"FAIL_pacman": status})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [["pacman", ["-Qtdq"]]])
                self.calls.unlink()
        result, calls = self.run_shell('cleanup', extra_env={"OUTPUT_pacman": "orphan-one\nodd name\n"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [["pacman", ["-Qtdq"]],
                                 ["sudo", ["pacman", "-Rns", "--", "orphan-one", "odd name"]]])

    def test_cleanup_never_removes_on_query_failure_and_propagates_remove_failure(self):
        self.provider("pacman")
        self.provider("sudo")
        result, calls = self.run_shell('cleanup', extra_env={"FAIL_pacman": "29"})
        self.assertEqual(result.returncode, 29, result.stderr)
        self.assertEqual(calls, [["pacman", ["-Qtdq"]]])
        self.calls.unlink()
        result, calls = self.run_shell('cleanup', extra_env={"OUTPUT_pacman": "one\n", "FAIL_sudo": "21"})
        self.assertEqual(result.returncode, 21, result.stderr)
        self.assertEqual(calls, [["pacman", ["-Qtdq"]], ["sudo", ["pacman", "-Rns", "--", "one"]]])

    def test_expac_inspection_uses_unprivileged_sorted_limited_pipelines(self):
        for name in ("expac", "sort", "tail", "nl"):
            self.provider(name)
        result, calls = self.run_shell('rip; riplong; big')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertCountEqual(calls, [
            ["expac", ["--timefmt=%Y-%m-%d %T", "%l\\t%n %v"]],
            ["sort", []], ["tail", ["-200"]], ["nl", []],
            ["expac", ["--timefmt=%Y-%m-%d %T", "%l\\t%n %v"]],
            ["sort", []], ["tail", ["-3000"]], ["nl", []],
            ["expac", ["-H", "M", "%m\\t%n"]], ["sort", ["-h"]], ["nl", []],
        ])

    def test_expac_pipeline_failure_and_missing_tools_do_not_report_success(self):
        for name in ("expac", "sort", "tail", "nl"):
            self.provider(name)
        result, calls = self.run_shell('rip', extra_env={"FAIL_expac": "24"})
        self.assertEqual(result.returncode, 24, result.stderr)
        self.assertCountEqual(calls, [["expac", ["--timefmt=%Y-%m-%d %T", "%l\\t%n %v"]],
                                      ["sort", []], ["tail", ["-200"]], ["nl", []]])
        (self.bin / "tail").unlink()
        self.calls.unlink()
        result, calls = self.run_shell('rip')
        self.assertEqual(result.returncode, 127, result.stderr)
        self.assertIn("tail", result.stderr)
        self.assertEqual(calls, [])

    def test_missing_providers_and_invalid_mutation_arguments_do_not_execute(self):
        self.provider("sudo")
        for invocation in ('sps pkg', 'spqo path', 'cleanup', 'depends pkg', 'list'):
            with self.subTest(invocation=invocation):
                result, calls = self.run_shell(invocation)
                self.assertEqual(result.returncode, 127, result.stderr)
                self.assertIn('pacman', result.stderr)
                self.assertEqual(calls, [])
                if self.calls.exists():
                    self.calls.unlink()
        self.provider("pacman")
        for invocation in ('spr', 'sprs', 'sps', 'update --noconfirm', 'upall --noconfirm',
                           'sps --noconfirm pkg', 'spr --noconfirm pkg',
                           'sprs --nodeps pkg', 'depends', 'depends x y', 'cleanup extra'):
            with self.subTest(invocation=invocation):
                result, calls = self.run_shell(invocation)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, [])
                if self.calls.exists():
                    self.calls.unlink()
        self.provider('paru')
        (self.bin / 'sudo').unlink()
        result, calls = self.run_shell('upall')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [['paru', ['-Syu']]])

    def test_depends_reports_required_by_only_and_propagates_provider_failure(self):
        self.provider('pacman')
        result, calls = self.run_shell('depends "sample pkg"', extra_env={
            'OUTPUT_pacman': 'Name            : sample pkg\nRequired By     : one  two\nDescription : fixture\n'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'one  two')
        self.assertEqual(calls, [['pacman', ['-Sii', '--', 'sample pkg']]])
        self.calls.unlink()
        result, calls = self.run_shell('depends sample', extra_env={
            'OUTPUT_pacman': 'Required By     : stale\n', 'FAIL_pacman': '31'})
        self.assertEqual(result.returncode, 31, result.stderr)
        self.assertNotIn('stale', result.stdout)
        self.assertEqual(calls, [['pacman', ['-Sii', '--', 'sample']]])

    def test_no_package_queries_on_source_reload_or_mac(self):
        for name in ('pacman', 'sudo', 'paru', 'expac', 'sort', 'tail', 'nl'):
            self.provider(name)
        result, calls = self.run_shell('source "$ZSHRC"; true')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])
        result, calls = self.run_shell('for name in sps spr sprs spqo spsii depends update upd '
                                       'upall upa rip riplong list listt listaur big cleanup; do '
                                       '(( $+functions[$name] || $+aliases[$name] )) && exit 30; done; true',
                                       ostype='darwin24')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])

    def test_no_migrated_bypass_helpers_and_failed_read_only_query_stays_failed(self):
        self.provider('pacman')
        result, calls = self.run_shell('for name in sprdd unlock rmpacmanlock paruskip yayskip '
                                       'trizenskip pksyua; do '
                                       '(( $+functions[$name] || $+aliases[$name] )) && exit 30; done; '
                                       'list', extra_env={'FAIL_pacman': '17'})
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(calls, [['pacman', ['-Qqe']]])

    def test_cleanup_with_orphans_and_missing_sudo_does_not_mutate(self):
        self.provider('pacman')
        result, calls = self.run_shell('cleanup', extra_env={'OUTPUT_pacman': 'one\n'})
        self.assertEqual(result.returncode, 127, result.stderr)
        self.assertIn('sudo', result.stderr)
        self.assertEqual(calls, [['pacman', ['-Qtdq']]])


if __name__ == "__main__":
    unittest.main()
