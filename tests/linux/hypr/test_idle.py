"""Run package entrypoints with a private PATH: no host daemon or desktop command."""

from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "linux/hypr/.config/hypr/start-hypridle.sh"
IDLE_CONFIG = ROOT / "linux/hypr/.config/hypr/hypridle.conf"
GUIDE = ROOT / "linux/hypr/.config/hypr/README.md"


class IdleConfigurationTests(unittest.TestCase):
    def test_guidance_identifies_exact_release_and_native_limits(self):
        guide = GUIDE.read_text()
        for expected in ("v0.1.8", "src/core/Hypridle.cpp", "hyprland-lock-notify-v1",
                         "inhibit_sleep = 3", "forced sleep", "delay inhibitor", "Owner QA"):
            with self.subTest(expected=expected):
                self.assertIn(expected, guide)

    def test_before_sleep_uses_acknowledgement_and_the_native_lock_event(self):
        conf = IDLE_CONFIG.read_text()
        general = re.findall(r"(?m)^general\s*\{([^}]*)\}", conf)
        self.assertEqual(len(general), 1)
        values = dict(re.findall(r"(?m)^\s*(\w+)\s*=\s*([^#\n]+)", general[0]))
        self.assertEqual(values.get("inhibit_sleep", "").strip(), "3")
        self.assertEqual(values.get("before_sleep_cmd", "").strip(), "loginctl lock-session")
        self.assertEqual(values.get("lock_cmd", "").strip(), "pidof hyprlock || hyprlock")
        self.assertEqual(values.get("after_sleep_cmd", "").strip(), "hyprctl dispatch dpms on")

    def test_fake_pre_sleep_events_and_resume_keep_the_existing_locker_guard(self):
        conf = IDLE_CONFIG.read_text()
        general = re.findall(r"(?m)^general\s*\{([^}]*)\}", conf)
        self.assertEqual(len(general), 1)
        values = {name: value.strip() for name, value in
                  re.findall(r"(?m)^\s*(\w+)\s*=\s*([^#\n]+)", general[0])}
        # Allow-list before executing any config value: only private provider names
        # can be resolved, and no real loginctl, hyprctl or locker can be reached.
        self.assertEqual(values["before_sleep_cmd"], "loginctl lock-session")
        self.assertEqual(values["lock_cmd"], "pidof hyprlock || hyprlock")
        self.assertEqual(values["after_sleep_cmd"], "hyprctl dispatch dpms on")
        with tempfile.TemporaryDirectory() as root:
            bin_dir = Path(root) / "bin"
            bin_dir.mkdir()
            log = Path(root) / "calls"
            for name, body in {
                "loginctl": ('printf "sleep-request:%s:%s\\n" "$1" "$2" >> "$FAKE_LOG"\n'
                             'test "$FAKE_REQUEST_FAIL" != yes || exit 19\n'
                             '/bin/sh -c "$FAKE_LOCK_CMD"\n'),
                "pidof": ('printf "check:%s\\n" "$1" >> "$FAKE_LOG"\n'
                          'test "$FAKE_LOCKER_RUNNING" = yes\n'),
                "hyprlock": ('printf "locker launched\\n" >> "$FAKE_LOG"\n'
                             'test "$FAKE_LOCKER_FAIL" != yes\n'),
                "hyprctl": 'printf "resume:%s:%s:%s\\n" "$1" "$2" "$3" >> "$FAKE_LOG"\n',
            }.items():
                path = bin_dir / name
                path.write_text("#!/bin/sh\n" + body)
                path.chmod(0o755)
            for running, request_fail, locker_fail, status, calls in (
                ("no", "no", "no", 0, ["sleep-request:lock-session:", "check:hyprlock", "locker launched"]),
                ("yes", "no", "no", 0, ["sleep-request:lock-session:", "check:hyprlock"]),
                ("no", "yes", "no", 19, ["sleep-request:lock-session:"]),
                ("no", "no", "yes", 1, ["sleep-request:lock-session:", "check:hyprlock", "locker launched"]),
            ):
                log.unlink(missing_ok=True)
                env = {"HOME": root, "PATH": str(bin_dir), "FAKE_LOG": str(log),
                       "FAKE_LOCK_CMD": values["lock_cmd"], "FAKE_LOCKER_RUNNING": running,
                       "FAKE_REQUEST_FAIL": request_fail, "FAKE_LOCKER_FAIL": locker_fail}
                sleep = subprocess.run(["/bin/sh", "-c", values["before_sleep_cmd"]],
                                       env=env, capture_output=True, text=True, timeout=5)
                self.assertEqual(sleep.returncode, status, sleep.stderr)
                self.assertEqual(log.read_text().splitlines(), calls)
                resume = subprocess.run(["/bin/sh", "-c", values["after_sleep_cmd"]],
                                        env=env, capture_output=True, text=True, timeout=5)
                self.assertEqual(resume.returncode, 0, resume.stderr)
                self.assertEqual(log.read_text().splitlines(), calls + ["resume:dispatch:dpms:on"])

    def test_idle_lock_request_is_after_five_minutes(self):
        conf = IDLE_CONFIG.read_text()
        listeners = re.findall(r"(?m)^listener\s*\{([^}]*)\}", conf)
        self.assertEqual(len(listeners), 1, "only the existing active lock listener")
        self.assertRegex(listeners[0], r"(?m)^\s*timeout\s*=\s*300\s*#\s*5min\b")

    def test_native_idle_lock_event_reuses_guarded_locker(self):
        conf = IDLE_CONFIG.read_text()
        listener = re.findall(r"(?m)^listener\s*\{([^}]*)\}", conf)[0]
        request = re.findall(r"(?m)^\s*on-timeout\s*=\s*([^#\n]+)", listener)
        locker = re.findall(r"(?m)^\s*lock_cmd\s*=\s*([^#\n]+)", conf)
        # Require known safe command grammar before exercising any config string.
        self.assertEqual([line.strip() for line in request], ["loginctl lock-session"])
        self.assertEqual([line.strip() for line in locker], ["pidof hyprlock || hyprlock"])
        with tempfile.TemporaryDirectory() as root:
            bin_dir = Path(root) / "bin"
            bin_dir.mkdir()
            log = Path(root) / "calls"
            for name, body in {
                "loginctl": 'printf "event:%s:%s\\n" "$1" "$2" >> "$FAKE_LOG"\n/bin/sh -c "$FAKE_LOCK_CMD"\n',
                "pidof": 'printf "check:%s\\n" "$1" >> "$FAKE_LOG"\ntest "$FAKE_LOCKER_RUNNING" = yes\n',
                "hyprlock": 'printf "locker launched\\n" >> "$FAKE_LOG"\n',
            }.items():
                path = bin_dir / name
                path.write_text("#!/bin/sh\n" + body)
                path.chmod(0o755)
            for running, expected in (
                ("no", ["event:lock-session:", "check:hyprlock", "locker launched"]),
                ("yes", ["event:lock-session:", "check:hyprlock"]),
            ):
                log.unlink(missing_ok=True)
                env = {"HOME": root, "PATH": str(bin_dir), "FAKE_LOG": str(log),
                       "FAKE_LOCK_CMD": locker[0].strip(), "FAKE_LOCKER_RUNNING": running}
                result = subprocess.run(
                    ["/bin/sh", "-c", request[0].strip()], env=env,
                    capture_output=True, text=True, check=False, timeout=5,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(log.read_text().splitlines(), expected)

    def test_sleep_policy_and_ordinary_inhibitors_remain_unmodified(self):
        conf = IDLE_CONFIG.read_text()
        self.assertRegex(conf, r"(?m)^\s*after_sleep_cmd = hyprctl dispatch dpms on\b")
        self.assertNotRegex(conf, r"(?m)^\s*ignore_\w+\s*=")


class IdleStartupTests(unittest.TestCase):
    def test_hyprland_can_execute_the_package_helper(self):
        self.assertTrue(HELPER.stat().st_mode & 0o111, "startup helper must be executable")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.log = self.home / "calls"
        self.env = {"HOME": str(self.home), "PATH": str(self.bin), "FAKE_LOG": str(self.log)}

    def provider(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def run_startup(self):
        return subprocess.run(
            ["/bin/sh", str(HELPER)], env=self.env, capture_output=True,
            text=True, check=False, timeout=5,
        )

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_missing_daemon_is_reported_without_attempting_a_launch(self):
        self.provider("hyprlock", "exit 0\n")
        self.provider("pgrep", "exit 1\n")
        result = self.run_startup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hypridle", result.stderr)
        self.assertIn("not found", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_missing_locker_prevents_an_unprotected_idle_daemon(self):
        self.provider("hypridle", "printf 'idle launched\\n' >> \"$FAKE_LOG\"\n")
        self.provider("pgrep", "exit 1\n")
        result = self.run_startup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hyprlock not found", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_existing_daemon_is_not_launched_again(self):
        self.provider("hypridle", "printf 'idle launched\\n' >> \"$FAKE_LOG\"\n")
        self.provider("hyprlock", "exit 0\n")
        self.provider("pgrep", "printf 'checked\\n' >> \"$FAKE_LOG\"\nexit 0\n")
        for _ in range(2):
            result = self.run_startup()
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), ["checked", "checked"])

    def test_unavailable_process_probe_does_not_start_a_second_daemon(self):
        self.provider("hypridle", "printf 'idle launched\\n' >> \"$FAKE_LOG\"\n")
        self.provider("hyprlock", "exit 0\n")
        for body in (None, "exit 2\n"):
            if body is not None:
                self.provider("pgrep", body)
            result = self.run_startup()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("pgrep", result.stderr)
            self.assertEqual(self.calls(), [])

    def test_failed_daemon_launch_is_reported_with_status(self):
        self.provider("hypridle", "printf 'idle launched\\n' >> \"$FAKE_LOG\"\nexit 23\n")
        self.provider("hyprlock", "exit 0\n")
        self.provider("pgrep", "printf 'probe:%s:%s\\n' \"$1\" \"$2\" >> \"$FAKE_LOG\"\nexit 1\n")
        result = self.run_startup()
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertIn("hypridle exited with status 23", result.stderr)
        self.assertEqual(self.calls(), ["probe:-x:hypridle", "idle launched"])

    def test_clean_daemon_exit_is_not_mistaken_for_active_protection(self):
        self.provider("hypridle", "printf 'idle launched\\n' >> \"$FAKE_LOG\"\nexit 0\n")
        self.provider("hyprlock", "exit 0\n")
        self.provider("pgrep", "exit 1\n")
        result = self.run_startup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hypridle exited with status 0", result.stderr)
        self.assertEqual(self.calls(), ["idle launched"])


if __name__ == "__main__":
    unittest.main()
