"""Finite, container-only exhaustion probes on a read-only root and bounded RAM."""
import errno
import json
import os
from pathlib import Path
import subprocess
import sys
import time


if not Path("/.dockerenv").is_file() or os.geteuid() != 10001:
    raise SystemExit("Resource probes must run only in the qualification container")


def counters(name):
    return {key: int(value) for key, value in
            (line.split() for line in (Path("/sys/fs/cgroup") / name).read_text().splitlines())}


def probe(mode):
    assert os.statvfs("/").f_flag & os.ST_RDONLY
    if mode == "pids":
        assert Path("/sys/fs/cgroup/pids.max").read_text().strip() == "32"
        before = counters("pids.events")["max"]
        children, denied = [], False
        try:
            # Finite attempts, not an uncontrolled fork bomb. All children are owned.
            for _ in range(40):
                try:
                    children.append(subprocess.Popen([sys.executable, "-B", "-c", "import time; time.sleep(20)"],
                                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
                except OSError as error:
                    assert error.errno == errno.EAGAIN
                    denied = True
                    break
            assert denied
            events = counters("pids.events")["max"] - before
            assert events > 0
            return {"denied": denied, "children_started": len(children), "limit": 32, "limit_events": events}
        finally:
            for child in children:
                child.kill()
            for child in children:
                child.wait(timeout=5)
    if mode == "memory":
        assert Path("/sys/fs/cgroup/memory.max").read_text().strip() == str(96 * 1024**2)
        assert Path("/sys/fs/cgroup/memory.swap.max").read_text().strip() == "0"
        before = counters("memory.events")
        child = subprocess.Popen([sys.executable, "-B", "-c",
                                  "chunks=[]\nfor _ in range(32):\n chunks.append(bytearray(8*1024**2))"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            exit_code = child.wait(timeout=15)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
        after = counters("memory.events")
        assert exit_code == -9 and after["oom_kill"] > before["oom_kill"]
        return {"child_exit": exit_code, "oom_kills": after["oom_kill"] - before["oom_kill"],
                "limit_bytes": 96 * 1024**2, "maximum_requested_bytes": 256 * 1024**2}
    if mode == "tmpfs":
        limit = 8 * 1024**2
        info = os.statvfs("/tmp")
        assert info.f_blocks * info.f_frsize == limit
        written, denied = 0, False
        with Path("/tmp/fill").open("wb", buffering=0) as stream:
            try:
                for _ in range(12):
                    written += stream.write(b"x" * 1024**2)
            except OSError as error:
                assert error.errno == errno.ENOSPC
                denied = True
        assert denied and 0 < written <= limit
        return {"denied": denied, "bytes_written": written, "limit_bytes": limit,
                "production_writable_layer_qualified": False}
    if mode == "cpu":
        quota, period = map(int, Path("/sys/fs/cgroup/cpu.max").read_text().split())
        assert quota / period == 0.25
        before = counters("cpu.stat")
        end = time.monotonic() + 3
        while time.monotonic() < end:
            pass
        after = counters("cpu.stat")
        periods = after["nr_throttled"] - before["nr_throttled"]
        assert periods > 0
        return {"cores": quota / period, "throttled_periods": periods,
                "throttled_usec": after["throttled_usec"] - before["throttled_usec"]}
    if mode == "logs":
        # Fixed total output, newline-delimited records for bounded rotation checks.
        for index in range(4096):
            sys.stdout.write(f"routine-log-{index:04d} " + "x" * 1006 + "\n")
        sys.stdout.flush()
        return {"lines_emitted": 4096, "last_line": 4095}
    raise ValueError("Unknown resource probe")


mode = sys.argv[1]
try:
    result = {"test": mode, "passed": True, "observed": probe(mode)}
except Exception as error:
    result = {"test": mode, "passed": False, "diagnostic": type(error).__name__}
print(json.dumps(result, sort_keys=True))
raise SystemExit(0 if result["passed"] else 1)
