"""Fixture-only public media/recording helper checks (no live providers)."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ZSHRC = Path(__file__).resolve().parents[3] / "common/zsh/.zshrc"


class MediaRecordingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="zsh-media-")
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
        self.provider("tty", "#!/bin/sh\necho /dev/fixture-tty\n")

    def provider(self, name, code=None):
        if code is None:
            code = '''#!/usr/bin/python3
import json, os, sys
with open(os.environ["CALLS"], "a") as output:
    output.write(json.dumps([os.path.basename(sys.argv[0]), sys.argv[1:]]) + "\\n")
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
            "PATH": str(self.bin), "BIN": str(self.bin),
            "FIXTURE": str(self.fixture), "ZSHRC": str(ZSHRC),
            "CALLS": str(self.calls), "COMMANDS": str(commands),
        }
        env.update(extra_env or {})
        # The existing macOS branch prepends legacy paths: reset before invoking.
        script = (f'OSTYPE={ostype}\nfpath=( "$FIXTURE" )\nsource "$ZSHRC"\n'
                  'path=( "$BIN" )\nsource "$COMMANDS"\n')
        result = subprocess.run(["/usr/bin/zsh", "-f", "-c", script], env=env,
                                cwd=self.root, capture_output=True, text=True, timeout=10)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        return result, calls

    def test_media_formats_forward_literal_urls_without_interpreting_options(self):
        self.provider("yt-dlp")
        self.provider("ffmpeg")
        url = "https://example.invalid/a?x=;$(touch escape)&y=[*]"
        for name, flags in (
            ("yta-aac", ["-x", "--audio-format", "aac"]),
            ("yta-best", ["-x", "--audio-format", "best"]),
            ("yta-flac", ["-x", "--audio-format", "flac"]),
            ("yta-mp3", ["-x", "--audio-format", "mp3"]),
            ("ytv-best", ["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio",
                          "--merge-output-format", "mp4"]),
        ):
            with self.subTest(name=name):
                result, calls = self.run_shell(f'{name} "$URL" "-hostile"', extra_env={"URL": url})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [["yt-dlp", flags + ["--", url, "-hostile"]]])
                self.assertFalse((self.root / "escape").exists())
                self.calls.unlink()

    def test_media_rejects_empty_input_and_missing_dependencies_without_provider_calls(self):
        for name in ("yta-aac", "yta-best", "yta-flac", "yta-mp3", "ytv-best"):
            with self.subTest(name=name):
                result, calls = self.run_shell(name)
                self.assertEqual(result.returncode, 2)
                self.assertIn("URL", result.stderr)
                self.assertEqual(calls, [])
                result, calls = self.run_shell(f"{name} https://example.invalid/item")
                self.assertEqual(result.returncode, 127)
                self.assertIn("yt-dlp", result.stderr)
                self.assertEqual(calls, [])
        self.provider("yt-dlp")
        result, calls = self.run_shell("yta-mp3 https://example.invalid/item")
        self.assertEqual(result.returncode, 127)
        self.assertIn("ffmpeg", result.stderr)
        self.assertEqual(calls, [])

    def test_media_propagates_downloader_error(self):
        self.provider("yt-dlp")
        self.provider("ffmpeg")
        result, calls = self.run_shell("ytv-best https://example.invalid/item",
                                       extra_env={"FAIL_yt-dlp": "29"})
        self.assertEqual(result.returncode, 29, result.stderr)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "yt-dlp")

    def test_wayland_recording_uses_audio_and_no_hardware_flags(self):
        self.provider("wf-recorder")
        for invocation, flags in (
            ("wsimplescreen", ["-a"]),
            ("wsimplescreenrecorder", ["-a", "-f", "recording.mp4"]),
            ('wsimplescreenrecorder "$OUTPUT"',
             ["-a", "-f", "movie [*] ; $(touch escape).mp4"]),
        ):
            with self.subTest(invocation=invocation):
                result, calls = self.run_shell(invocation, extra_env={
                    "OUTPUT": "movie [*] ; $(touch escape).mp4"})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [["wf-recorder", flags]])
                self.assertFalse((self.root / "escape").exists())
                self.calls.unlink()

    def test_recording_rejects_invalid_outputs_and_never_overwrites_existing_file(self):
        self.provider("wf-recorder")
        (self.root / "recording.mp4").write_text("original")
        (self.root / "linked.mp4").symlink_to("missing")
        for invocation, expected in (
            ("wsimplescreen unexpected", "no arguments"),
            ('wsimplescreenrecorder ""', "output filename"),
            ("wsimplescreenrecorder a.mp4 b.mp4", "output filename"),
            ("wsimplescreenrecorder movie.mkv", "output filename"),
            ("wsimplescreenrecorder", "already exists"),
            ("wsimplescreenrecorder linked.mp4", "already exists"),
        ):
            with self.subTest(invocation=invocation):
                result, calls = self.run_shell(invocation)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
                self.assertEqual(calls, [])
        self.assertEqual((self.root / "recording.mp4").read_text(), "original")

    def test_recording_missing_provider_and_failure_report_status(self):
        result, calls = self.run_shell("wsimplescreenrecorder")
        self.assertEqual(result.returncode, 127)
        self.assertIn("wf-recorder", result.stderr)
        self.assertEqual(calls, [])
        result, calls = self.run_shell("wsimplescreen")
        self.assertEqual(result.returncode, 127)
        self.assertIn("wf-recorder", result.stderr)
        self.assertEqual(calls, [])
        self.provider("wf-recorder")
        for helper in ("wsimplescreen", "wsimplescreenrecorder"):
            with self.subTest(helper=helper):
                result, calls = self.run_shell(helper, extra_env={"FAIL_wf-recorder": "27"})
                self.assertEqual(result.returncode, 27, result.stderr)
                self.assertEqual(calls[0][0], "wf-recorder")
                self.calls.unlink()

    def test_recorders_are_linux_only_and_reload_is_inert(self):
        self.provider("yt-dlp")
        self.provider("ffmpeg")
        self.provider("wf-recorder")
        result, calls = self.run_shell('source "$ZSHRC"; '
                                       '(( $+functions[wsimplescreen] && $+functions[wsimplescreenrecorder] ))',
                                       ostype="darwin24")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])
        result, calls = self.run_shell('source "$ZSHRC"; '
                                       '(( $+functions[wsimplescreen] && $+functions[wsimplescreenrecorder] '
                                       '&& $+functions[yta-mp3] ))')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])
        self.assertFalse((self.root / "recording.mp4").exists())


if __name__ == "__main__":
    unittest.main()
