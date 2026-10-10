"""Native Zsh startup in a disposable home with fixture-only providers."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ZSHRC = Path(__file__).resolve().parents[3] / "common/zsh/.zshrc"
ZSH = "/usr/bin/zsh"


class ShellEnvironmentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="zsh-environment-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.xdg = self.root / "xdg"
        self.xdg.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.fixture = self.root / "functions"
        self.fixture.mkdir()
        (self.fixture / "compinit").write_text('print -r -- compinit >> "$TRACE"\n')
        self.provider("tty", '#!/bin/sh\necho /dev/fixture-tty\n')
        self.trace = self.root / "trace"

    def provider(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(0o755)

    def loader(self, name, text):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def run_shell(self, *, ostype="linux-gnu", setup="", times=1):
        # -f disables user rc files; no inherited PATH/HOME/XDG or provider access.
        env = {
            "HOME": str(self.home), "ZDOTDIR": str(self.root),
            "XDG_DATA_HOME": str(self.xdg),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_CACHE_HOME": str(self.root / "cache"),
            # An explicit missing selection keeps tests independent of the
            # host's actual /opt/cuda installation.
            "CUDA_HOME": str(self.root / "missing-cuda"),
            "PATH": str(self.bin), "ZSHRC": str(ZSHRC),
            "TRACE": str(self.trace), "FIXTURE": str(self.fixture),
        }
        script = f'''OSTYPE={ostype}
fpath=( "$FIXTURE" )
{setup}
source "$ZSHRC"
print -r -- "RESULT:first_path=$PATH"
'''
        if times == 2:
            script += 'source "$ZSHRC"\n'
        script += '''for name in EDITOR VISUAL HISTFILE HISTSIZE SAVEHIST CUDA_HOME GPG_TTY PATH; do
  print -r -- "RESULT:$name=${(P)name}"
done
for option in appendhistory histignorealldups histignorespace histsavenodups; do
  print -r -- "RESULT:option_$option=$options[$option]"
done
print -r -- "RESULT:matcher=$(zstyle -L ':completion:*' matcher-list)"
for name in v vim reload pacman; do
  print -r -- "RESULT:alias_$name=$aliases[$name]"
done
'''
        result = subprocess.run([ZSH, "-f", "-c", script], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(result.stderr, result.stderr)
        self.assertTrue(all(line.startswith("RESULT:") for line in result.stdout.splitlines()),
                        result.stdout)
        values = dict(line.removeprefix("RESULT:").split("=", 1)
                      for line in result.stdout.splitlines() if line.startswith("RESULT:"))
        trace = self.trace.read_text().splitlines() if self.trace.exists() else []
        return values, trace

    def test_defaults_and_user_path_are_stable_across_reload(self):
        (self.home / ".bin").mkdir()
        (self.home / ".local/bin").mkdir(parents=True)
        values, trace = self.run_shell(times=2)
        expected = f"{self.home}/.local/bin:{self.home}/.bin:{self.bin}"
        self.assertEqual(values["first_path"], expected)
        self.assertEqual(values["PATH"], expected)
        self.assertEqual(values["EDITOR"], "nvim")
        self.assertEqual(values["VISUAL"], "nvim")
        self.assertEqual(values["HISTFILE"], f"{self.home}/.zsh_history")
        self.assertEqual(values["HISTSIZE"], "10000")
        self.assertEqual(values["SAVEHIST"], "10000")
        for option in ("appendhistory", "histignorealldups", "histignorespace", "histsavenodups"):
            self.assertEqual(values[f"option_{option}"], "on")
        self.assertEqual(trace, ["compinit", "compinit"])

    def test_explicit_cuda_installation_is_added_once_without_replacing_selection(self):
        cuda = self.root / "cuda install"
        (cuda / "bin").mkdir(parents=True)
        values, _ = self.run_shell(setup=f'CUDA_HOME="{cuda}"; export CUDA_HOME', times=2)
        self.assertEqual(values["CUDA_HOME"], str(cuda))
        self.assertEqual(values["first_path"], f"{cuda}/bin:{self.bin}")
        self.assertEqual(values["PATH"], values["first_path"])

    def test_existing_cuda_path_and_absent_optional_directories_do_not_shift_path(self):
        cuda = self.root / "cuda"
        (cuda / "bin").mkdir(parents=True)
        setup = f'CUDA_HOME="{cuda}"; export CUDA_HOME; path=( "{cuda}/bin" "$PATH" )'
        values, trace = self.run_shell(setup=setup, times=2)
        self.assertEqual(values["PATH"], f"{cuda}/bin:{self.bin}")
        self.assertEqual(values["first_path"], values["PATH"])
        self.assertEqual(trace, ["compinit", "compinit"])

    def test_missing_explicit_cuda_installation_is_not_added(self):
        missing = self.root / "missing"
        values, _ = self.run_shell(setup=f'CUDA_HOME="{missing}"; export CUDA_HOME')
        self.assertEqual(values["CUDA_HOME"], str(missing))
        self.assertEqual(values["PATH"], str(self.bin))

    def test_caller_paths_and_history_settings_keep_their_order(self):
        (self.home / ".bin").mkdir()
        (self.home / ".local/bin").mkdir(parents=True)
        missing_cuda = self.root / "missing cuda"
        setup = (f'path=( "{self.home}/.bin" "$PATH" ); '
                 f'EDITOR=helix VISUAL=emacs HISTFILE="{self.root}/chosen history"; '
                 f'HISTSIZE=222 SAVEHIST=333 CUDA_HOME="{missing_cuda}"; export CUDA_HOME')
        values, trace = self.run_shell(setup=setup, times=2)
        expected = f"{self.home}/.local/bin:{self.home}/.bin:{self.bin}"
        self.assertEqual(values["PATH"], expected)
        self.assertEqual(values["EDITOR"], "helix")
        self.assertEqual(values["VISUAL"], "emacs")
        self.assertEqual(values["HISTFILE"], f"{self.root}/chosen history")
        self.assertEqual(values["HISTSIZE"], "222")
        self.assertEqual(values["SAVEHIST"], "333")
        self.assertEqual(values["CUDA_HOME"], str(missing_cuda))
        self.assertEqual(trace, ["compinit", "compinit"])

    def test_fake_plugins_prompt_and_external_loaders_preserve_order_and_authority(self):
        zap = self.xdg / "zap/zap.zsh"
        zap.parent.mkdir()
        zap.write_text('plug() { print -r -- "plug:$1" >> "$TRACE"; }\n')
        self.provider("starship", '#!/bin/sh\nprintf \'print -r -- starship-eval >> "$TRACE"\\n\'\n')
        self.loader(".env", 'print -r -- env >> "$TRACE"\nEDITOR=environment-editor\n')
        self.loader("google-cloud-sdk/path.zsh.inc",
                    'print -r -- cloud-path >> "$TRACE"\npath=( cloud-bin $path )\n')
        self.loader("google-cloud-sdk/completion.zsh.inc",
                    'print -r -- cloud-completion >> "$TRACE"\n')
        self.loader(".config/envman/load.sh",
                    'print -r -- envman >> "$TRACE"\nEDITOR=envman-editor\n')
        values, trace = self.run_shell()
        self.assertEqual(trace, ["plug:zsh-users/zsh-autosuggestions",
                                 "plug:zap-zsh/supercharge",
                                 "plug:zsh-users/zsh-syntax-highlighting",
                                 "starship-eval", "compinit", "env", "cloud-path",
                                 "cloud-completion", "envman"])
        self.assertEqual(values["EDITOR"], "envman-editor")
        self.assertEqual(values["PATH"], f"cloud-bin:{self.bin}")
        self.assertEqual(values["alias_v"], "nvim")
        self.assertEqual(values["alias_vim"], "nvim")
        self.assertEqual(values["alias_reload"], "source ~/.zshrc")
        self.assertIn("m:{a-z}={A-Za-z}", values["matcher"])
        self.assertEqual(values["GPG_TTY"], "/dev/fixture-tty")
        self.assertEqual(values["alias_pacman"], "sudo pacman")

    def test_mac_branch_keeps_existing_brew_setup_without_linux_alias(self):
        self.provider("brew", '#!/bin/sh\nprintf "/fixture/brew/%s\\n" "$2"\n')
        values, trace = self.run_shell(ostype="darwin24")
        self.assertEqual(values["PATH"],
                         f"/opt/python@3.12/libexec/bin:/fixture/brew/ruby/bin:"
                         f"/opt/homebrew/opt/openjdk@11/bin:{self.bin}")
        self.assertEqual(values["alias_pacman"], "")
        self.assertEqual(trace, ["compinit"])

    def test_mac_without_optional_brew_or_plugins_still_loads(self):
        values, trace = self.run_shell(ostype="darwin24")
        self.assertEqual(values["PATH"], f"/opt/python@3.12/libexec/bin:{self.bin}")
        self.assertEqual(values["alias_pacman"], "")
        self.assertEqual(trace, ["compinit"])


if __name__ == "__main__":
    unittest.main()
