"""Native Zsh shortcut behavior with non-delegating fixture-only providers."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ZSHRC = Path(__file__).resolve().parents[3] / "common/zsh/.zshrc"


class SnapshotsConfigEditingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="zsh-snapshot-edits-", dir="/tmp/opencode")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home with spaces"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.fixture = self.root / "functions"
        self.fixture.mkdir()
        (self.fixture / "compinit").write_text(":\n")
        self.calls = self.root / "calls"
        self.provider("tty", '#!/bin/sh\necho /dev/fixture-tty\n')

    def provider(self, name, code=None):
        target = self.bin / name
        target.write_text(code or '''#!/usr/bin/python3
import json, os, sys
name = os.path.basename(sys.argv[0])
with open(os.environ['CALLS'], 'a') as calls:
    calls.write(json.dumps([name, sys.argv[1:]]) + '\\n')
sys.exit(int(os.environ.get('FAIL_' + name, '0')))
''')
        target.chmod(0o755)

    def run_shell(self, invocation, *, ostype="linux-gnu", extra_env=None):
        commands = self.root / "commands.zsh"
        commands.write_text(invocation + "\n")
        env = {
            "HOME": str(self.home), "ZDOTDIR": str(self.root),
            "XDG_DATA_HOME": str(self.root / "xdg"),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_CACHE_HOME": str(self.root / "cache"),
            "CUDA_HOME": str(self.root / "missing-cuda"),
            "PATH": str(self.bin), "BIN": str(self.bin),
            "ZSHRC": str(ZSHRC), "FIXTURE": str(self.fixture),
            "CALLS": str(self.calls), "COMMANDS": str(commands),
        }
        env.update(extra_env or {})
        # No inherited provider path, personal loader, real sudo or /etc reads.
        # The existing macOS startup branch changes PATH; restore fixture PATH.
        script = (f'OSTYPE={ostype}\nfpath=( "$FIXTURE" )\nsource "$ZSHRC"\n'
                  'path=( "$BIN" )\nsource "$COMMANDS"\n')
        result = subprocess.run(["/usr/bin/zsh", "-f", "-c", script], env=env,
                                cwd=self.root, capture_output=True, text=True, timeout=10)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        return result, calls

    def test_btrfs_inspection_is_explicit_and_limited_to_root(self):
        self.provider("sudo")
        self.provider("btrfs")
        result, calls = self.run_shell('source "$ZSHRC"; btrfsfs; btrfsli')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [["sudo", ["btrfs", "filesystem", "df", "/"]],
                                 ["sudo", ["btrfs", "subvolume", "list", "/", "-t"]]])

    def test_snapper_lists_selected_existing_config_and_creates_described_snapshots(self):
        self.provider("sudo")
        self.provider("snapper")
        description = 'pre upgrade ; $(touch escape) [*]'
        result, calls = self.run_shell('snapli; snapli home; snapcr "$DESCRIPTION"; snapch',
                                       extra_env={"DESCRIPTION": description})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [["sudo", ["snapper", "-c", "root", "list"]],
                                 ["sudo", ["snapper", "-c", "home", "list"]],
                                 ["sudo", ["snapper", "-c", "root", "create", "-d", description]],
                                 ["sudo", ["snapper", "-c", "home", "create"]]])
        self.assertFalse((self.root / "escape").exists())

    def test_snapshot_shortcuts_reject_invalid_input_and_missing_or_failed_providers(self):
        self.provider("sudo")
        for invocation in ("btrfsfs extra", "btrfsli /other", "snapli other",
                           "snapli root home", "snapcr --cleanup-algorithm number",
                           'snapch ""'):
            with self.subTest(invocation=invocation):
                result, calls = self.run_shell(invocation)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(calls, [])
        for invocation, missing in (("btrfsfs", "btrfs"), ("snapcr", "snapper")):
            with self.subTest(invocation=invocation):
                result, calls = self.run_shell(invocation)
                self.assertEqual(result.returncode, 127, result.stderr)
                self.assertIn(missing, result.stderr)
                self.assertEqual(calls, [])
        self.provider("btrfs")
        self.provider("snapper")
        for invocation in ("btrfsli", "snapli home", "snapch"):
            with self.subTest(invocation=invocation):
                result, calls = self.run_shell(invocation, extra_env={"FAIL_sudo": "41"})
                self.assertEqual(result.returncode, 41, result.stderr)
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0][0], "sudo")
                self.calls.unlink()

    def test_user_editors_are_chosen_at_invocation_and_forward_literal_paths(self):
        self.provider("nvim")
        self.provider("code")
        (self.home / ".zshrc").write_text("fixture\n")
        (self.home / ".bashrc").write_text("fixture\n")
        (self.home / ".config/fish").mkdir(parents=True)
        (self.home / ".config/fish/config.fish").write_text("fixture\n")
        argument = 'extra [*] ; $(touch escape)'
        result, calls = self.run_shell('nz; EDITOR="code --wait"; nb "$ARGUMENT"; '
                                       'EDITOR=nvim; nf', extra_env={"ARGUMENT": argument})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [["nvim", ["--", str(self.home / ".zshrc")]],
                                 ["code", ["--wait", "--", str(self.home / ".bashrc"), argument]],
                                 ["nvim", ["--", str(self.home / ".config/fish/config.fish")]]])
        self.assertFalse((self.root / "escape").exists())

    def test_privileged_shortcuts_use_only_sudoedit_for_fixed_source_files(self):
        self.provider("sudoedit")
        # Override only the file-existence predicate; never stat/read host /etc.
        fixture = '_config_edit_target_exists() { [[ $1 == /etc/* ]]; }; '
        targets = {
            "npacman": "/etc/pacman.conf", "nmirrorlist": "/etc/pacman.d/mirrorlist",
            "narcomirrorlist": "/etc/pacman.d/arcolinux-mirrorlist",
            "ngrub": "/etc/default/grub", "nmkinitcpio": "/etc/mkinitcpio.conf",
            "nfstab": "/etc/fstab", "nhosts": "/etc/hosts",
            "nhostname": "/etc/hostname", "nresolv": "/etc/resolv.conf",
            "nnsswitch": "/etc/nsswitch.conf", "nsamba": "/etc/samba/smb.conf",
            "ngnupgconf": "/etc/pacman.d/gnupg/gpg.conf",
            "nvconsole": "/etc/vconsole.conf", "nsddm": "/etc/sddm.conf",
            "nsddmk": "/etc/sddm.conf.d/kde_settings.conf",
            "nlxdm": "/etc/lxdm/lxdm.conf",
            "nlightdm": "/etc/lightdm/lightdm.conf",
            "nplymouth": "/etc/plymouth/plymouthd.conf",
        }
        result, calls = self.run_shell(fixture + "; ".join(targets))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [["sudoedit", ["--", target]] for target in targets.values()])

    def test_privileged_edit_rejects_missing_target_tool_and_extra_paths(self):
        self.provider("sudoedit")
        for invocation, expected in (
            ("_config_edit_target_exists() { return 1; }; ngrub", "target not found"),
            ("_config_edit_target_exists() { return 0; }; nhosts /etc/shadow", "no arguments"),
        ):
            with self.subTest(invocation=invocation):
                result, calls = self.run_shell(invocation)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(expected, result.stderr)
                self.assertEqual(calls, [])
        (self.bin / "sudoedit").unlink()
        result, calls = self.run_shell('_config_edit_target_exists() { return 0; }; ngrub')
        self.assertEqual(result.returncode, 127, result.stderr)
        self.assertIn("sudoedit", result.stderr)
        self.assertEqual(calls, [])

    def test_privileged_edit_propagates_sudoedit_failure_without_running_root_editor(self):
        self.provider("sudoedit")
        self.provider("sudo")
        self.provider("nvim")
        result, calls = self.run_shell('_config_edit_target_exists() { return 0; }; '
                                       'EDITOR=nvim; ngrub', extra_env={"FAIL_sudoedit": "37"})
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertEqual(calls, [["sudoedit", ["--", "/etc/default/grub"]]])

    def test_user_edit_rejects_missing_targets_and_editors_and_propagates_failures(self):
        result, calls = self.run_shell("nz")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("target not found", result.stderr)
        self.assertEqual(calls, [])
        (self.home / ".zshrc").write_text("fixture\n")
        result, calls = self.run_shell("nz")
        self.assertEqual(result.returncode, 127, result.stderr)
        self.assertIn("nvim", result.stderr)
        self.assertEqual(calls, [])
        self.provider("nvim")
        result, calls = self.run_shell("nz", extra_env={"FAIL_nvim": "33"})
        self.assertEqual(result.returncode, 33, result.stderr)
        self.assertEqual(calls, [["nvim", ["--", str(self.home / ".zshrc")]]])

    def test_user_editor_selection_is_not_evaluated_as_shell_code(self):
        self.provider("code")
        (self.home / ".zshrc").write_text("fixture\n")
        result, calls = self.run_shell('EDITOR="$UNTRUSTED"; nz', extra_env={
            "UNTRUSTED": "code --wait ; $(touch escape)"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [["code", ["--wait", ";", "$(touch", "escape)",
                                           "--", str(self.home / ".zshrc")]]])
        self.assertFalse((self.root / "escape").exists())

    def test_linux_only_shortcuts_have_no_startup_effect_and_are_absent_on_mac(self):
        for provider in ("sudo", "btrfs", "snapper", "sudoedit", "nvim"):
            self.provider(provider)
        result, calls = self.run_shell('source "$ZSHRC"; for name in btrfsfs btrfsli '
                                       'snapli snapcr snapch npacman ngrub; do '
                                       '(( $+functions[$name] || $+aliases[$name] )) || exit 30; '
                                       'done; for name in nconfgrub snapcroot snapchome; do '
                                       '(( $+functions[$name] || $+aliases[$name] )) && exit 31; done; true')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])
        result, calls = self.run_shell('source "$ZSHRC"; for name in btrfsfs btrfsli '
                                       'snapli snapcr snapch npacman ngrub nconfgrub '
                                       'snapcroot snapchome; do '
                                       '(( $+functions[$name] || $+aliases[$name] )) && exit 30; '
                                       'done; (( $+functions[nz] && $+functions[nb] && $+functions[nf] ))',
                                       ostype="darwin24")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])

    def test_user_edit_remains_available_on_mac_and_uses_late_visual_if_editor_unset(self):
        self.provider("code")
        (self.home / ".zshrc").write_text("fixture\n")
        result, calls = self.run_shell('unset EDITOR; VISUAL="code --wait"; nz',
                                       ostype="darwin24")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [["code", ["--wait", "--", str(self.home / ".zshrc")]]])


if __name__ == "__main__":
    unittest.main()
