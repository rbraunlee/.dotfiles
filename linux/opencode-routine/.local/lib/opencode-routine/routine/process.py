"""Bounded host subprocesses: trusted Git/Docker only, never repository scripts."""
import os
import selectors
import signal
import subprocess
import time

from .contracts import RoutineError, require


def host_environment():
    # No user Git includes, auth helpers, Docker contexts, SSH agent or provider keys.
    return {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
            "GIT_ATTR_NOSYSTEM": "1", "GIT_NO_LAZY_FETCH": "1", "GIT_OPTIONAL_LOCKS": "0",
            "DOCKER_CONFIG": "/nonexistent", "PYTHONDONTWRITEBYTECODE": "1"}


def run_bounded(argv, *, timeout, max_bytes=1024 * 1024, env=None, output=None, cwd=None):
    """Drain stdout without unlimited memory/disk; discard raw stderr, fail safely."""
    require(timeout > 0, "command_timeout", "Preparation/command budget exhausted")
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, env=env or host_environment(), cwd=cwd,
                               start_new_session=True)
    chunks, size = [], 0
    deadline = time.monotonic() + timeout
    completed = False
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                require(remaining > 0, "command_timeout", "Host adapter command exceeded its deadline")
                for key, _ in selector.select(min(remaining, 0.1)):
                    data = os.read(key.fd, 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    size += len(data)
                    require(size <= max_bytes, "output_limit", "Host adapter output exceeds its approved bound")
                    if output is None:
                        chunks.append(data)
                    else:
                        output.write(data)
            try:
                code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired as exc:
                raise RoutineError("command_timeout", "Host adapter command exceeded its deadline") from exc
        require(code == 0, "adapter_failed", "Trusted host adapter command failed; raw output was not exported")
        completed = True
        return b"".join(chunks)
    finally:
        if not completed:
            # The direct child may already have exited while descendants still
            # hold the pipe open. Terminate the owned group, not just a live parent.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        process.stdout.close()
