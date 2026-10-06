"""Container-only offline baseline. Never invoke this entry point on the host."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time


ASSET_NAMES = ("Dockerfile", "worker.py", "opencode.json", "proxy.py")
SERVER = "http://127.0.0.1:4096"
PROJECT = Path("/home/worker/project")
EVIDENCE = Path("/home/worker/evidence.json")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    identity = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while data := stream.read(65536):
            identity.update(data)
    return identity.hexdigest()


class WorkerFailure(Exception):
    pass


def service_password(path):
    """Read the foreground server's private, generated password; never export it."""
    try:
        with Path(path).open('rb') as stream:
            data = stream.read(65536)
    except FileNotFoundError:
        return None
    for line in data.decode('utf-8', errors='replace').splitlines():
        if line.startswith('server password '):
            password = line.removeprefix('server password ')
            if 1 <= len(password) <= 512 and not any(character.isspace() for character in password):
                return password
    return None


def verify_mounts(context, baseline, records, handoff=Path("/handoff"), inputs=Path("/inputs")):
    """Check both read-only snapshot locations before running repository commands."""
    mounts = context["profile"]["mounts"]
    expected = context["mounts"]
    if not isinstance(expected, list) or len(mounts) != len(expected):
        raise WorkerFailure("input_snapshot_mismatch")
    remaining_bytes = context["profile"]["resources"]["disk_mb"] * 1024 * 1024
    for index, (mount, record) in enumerate(zip(mounts, expected), 1):
        if (not isinstance(record, dict) or set(record) != {"source", "target", "sha256", "size_bytes"}
                or type(record["size_bytes"]) is not int or not 0 <= record["size_bytes"] <= remaining_bytes
                or any(record[key] != mount[key] for key in ("source", "target", "sha256"))):
            raise WorkerFailure("input_snapshot_mismatch")
        target = PurePosixPath(record["target"])
        if (not target.is_relative_to("/inputs") or target == PurePosixPath("/inputs")
                or ".." in target.parts or str(target) != record["target"] or mount["read_only"] is not True):
            raise WorkerFailure("input_snapshot_mismatch")
        for path in (handoff / "mounts" / f"{index:04d}.bin", inputs / target.relative_to("/inputs")):
            baseline.remaining()
            if not os.statvfs(path).f_flag & os.ST_RDONLY:
                raise WorkerFailure("input_snapshot_mismatch")
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size != record["size_bytes"]:
                    raise WorkerFailure("input_snapshot_mismatch")
                identity, size = hashlib.sha256(), 0
                while data := stream.read(min(65536, record["size_bytes"] - size + 1)):
                    baseline.remaining()
                    size += len(data)
                    if size > record["size_bytes"]:
                        raise WorkerFailure("input_snapshot_mismatch")
                    identity.update(data)
                if size != record["size_bytes"] or identity.hexdigest() != record["sha256"]:
                    raise WorkerFailure("input_snapshot_mismatch")
        records.append(record.copy())
        remaining_bytes -= record["size_bytes"]


class Baseline:
    def __init__(self, context, api=None, clock=time.time, sleep=time.sleep):
        self.context = context
        self.clock = clock
        self.sleep = sleep
        self.api = api or self.call_api
        self.password = None
        self.operation_deadline = None
        self.active_shell_id = None

    def remaining(self):
        seconds = self.context["deadline_epoch"] - self.clock()
        if seconds <= 0:
            raise WorkerFailure("runtime_timeout")
        return seconds

    def call_api(self, method, path, body=None):
        # Explicit container-local server, never shared host-service discovery.
        if self.password is None:
            raise WorkerFailure("service_auth_unavailable")
        command = ["/usr/local/bin/opencode", "api", "--server", SERVER, method, path]
        if body is not None:
            command.extend(["--data", json.dumps(body)])
        with tempfile.TemporaryFile() as output:
            environment = {**os.environ, "OPENCODE_PASSWORD": self.password}
            timeout = min(15, self.remaining())
            if self.operation_deadline is not None:
                timeout = min(timeout, self.operation_deadline - self.clock())
                if timeout <= 0:
                    raise WorkerFailure("command_timeout")
            result = subprocess.run(command, cwd="/control", stdout=output, stderr=subprocess.DEVNULL,
                                    timeout=timeout, check=False, env=environment)
            if result.returncode:
                raise WorkerFailure("api_failed")
            output.seek(0)
            data = output.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise WorkerFailure("api_output_limit")
        return json.loads(data) if data.strip() else None

    def command(self, name, stage, entry):
        deadline = min(self.context["deadline_epoch"], self.clock() + entry["timeout_seconds"])
        self.operation_deadline = deadline
        try:
            return self.execute_command(name, stage, entry, deadline)
        except (subprocess.TimeoutExpired, WorkerFailure) as error:
            if isinstance(error, WorkerFailure) and str(error) != "command_timeout":
                raise
            # A hanging API client cannot extend an individual command's budget.
            # Cancel a known command within a separate, bounded cleanup window.
            # If creation was ambiguous or cancellation fails, main() stops the service
            # and host supervision stops the container; neither can establish a pass.
            if self.active_shell_id is not None:
                self.operation_deadline = min(self.context["deadline_epoch"], self.clock() + 2)
                self.api("delete", "/api/shell/" + self.active_shell_id)
                return self.command_evidence(name, stage, entry, self.active_shell_id,
                                             {"status": "timeout", "exit": None}, {"output": "", "truncated": True})
            raise WorkerFailure("command_timeout") from error
        finally:
            self.operation_deadline = None
            self.active_shell_id = None

    def execute_command(self, name, stage, entry, deadline):
        response = self.api("post", "/api/shell", {
            "command": shlex.join(entry["argv"]), "cwd": str(PROJECT),
            "timeout": max(1, int((deadline - self.clock()) * 1000)),
            "metadata": {"routine_command_id": name, "routine_run_id": self.context["request"]["run_id"]},
        })
        info = response["data"]
        shell_id = info["id"]
        if not isinstance(shell_id, str) or not re.fullmatch(r"sh_[A-Za-z0-9_-]+", shell_id):
            raise WorkerFailure("api_failed")
        self.active_shell_id = shell_id
        while info["status"] == "running":
            self.remaining()
            if self.clock() >= deadline:
                # Removing the command terminates it; raw output is never exported.
                self.operation_deadline = min(self.context["deadline_epoch"], self.clock() + 2)
                self.api("delete", "/api/shell/" + shell_id)
                info = {"status": "timeout", "exit": None}
                break
            self.sleep(0.05)
            info = self.api("get", "/api/shell/" + shell_id)["data"]
        if self.clock() >= deadline:
            # Conservative admission: late-observed success is not a timely check.
            info = {"status": "timeout", "exit": None}
        # Fingerprint only a bounded output page. Raw text remains inside the stopped
        # container, avoiding an unverifiable regex-based claim of secret redaction.
        output = {"output": "", "truncated": True}
        if info["status"] != "timeout":
            output = self.api("get", "/api/shell/" + shell_id + "/output?limit=65536")["data"]
            if self.clock() >= deadline:
                info = {"status": "timeout", "exit": None}
                output = {"output": "", "truncated": True}
        return self.command_evidence(name, stage, entry, shell_id, info, output)

    @staticmethod
    def command_evidence(name, stage, entry, shell_id, info, output):
        return {"id": name, "stage": stage, "argv_sha256": sha(canonical(entry["argv"])),
                "shell_id": shell_id, "status": info["status"], "exit": info.get("exit"),
                "output_sha256": sha(output["output"].encode()), "output_truncated": output["truncated"]}


def git(args, baseline):
    subprocess.run(["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *args],
                   cwd="/control", stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=min(60, baseline.remaining()), check=True)


def write_evidence(value):
    # The bounded host log driver is outside the writable-layer quota. Emit only
    # the allowlisted result, never exceptions, service logs or command output.
    # A full layer must not prevent evidence collection or trigger file deletion.
    data = canonical(value)
    if len(data) > 1024 * 1024:
        raise WorkerFailure("api_output_limit")
    try:
        temporary = EVIDENCE.with_suffix(".tmp")
        with temporary.open("wb") as stream:
            stream.write(data + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, EVIDENCE)
    except OSError:
        # Local retention is best effort; host admission still validates the exact
        # result and the container exit. Do not export the OS error or raw paths.
        pass
    sys.stdout.buffer.write(canonical({"routine_evidence": value}) + b"\n")
    sys.stdout.buffer.flush()


def main():
    # Refuse accidental host execution even if a caller points at a fixture file.
    if not Path("/.dockerenv").is_file() or os.geteuid() != 10001:
        raise SystemExit("This entry point runs only inside the routine worker container")
    context = json.loads(Path("/handoff/context.json").read_bytes())
    baseline = Baseline(context)
    result = {"version": 2, "request": context["request"], "baseline": context["baseline"],
              "bundle_sha256": context["bundle_sha256"], "profile_sha256": context["profile_sha256"],
              "input_bundle_sha256": context["input_bundle_sha256"], "outcome": "failed",
              "service": None, "checks": [], "mounts": [], "diagnostic": "bootstrap_failed"}
    server = None
    server_log = None
    try:
        assets = Path(__file__).resolve().parent
        actual_bundle = sha(canonical({name: file_sha(assets / name) for name in ASSET_NAMES}))
        if actual_bundle != context["bundle_sha256"] or file_sha("/handoff/repository.bundle") != context["input_bundle_sha256"]:
            raise WorkerFailure("input_identity_mismatch")
        profile_bytes = context["planning"][".opencode/routine/project.json"].encode()
        if sha(profile_bytes) != context["profile_sha256"] or json.loads(profile_bytes) != context["profile"]:
            raise WorkerFailure("input_identity_mismatch")
        verify_mounts(context, baseline, result["mounts"])
        baseline.remaining()
        git(["clone", "--no-checkout", "/handoff/repository.bundle", str(PROJECT)], baseline)
        git(["-C", str(PROJECT), "switch", "--create", "routine/" + context["request"]["run_id"], context["baseline"]["commit"]], baseline)
        if not (PROJECT / ".git").is_dir() or (PROJECT / ".git/objects/info/alternates").exists():
            raise WorkerFailure("unsafe_clone")
        server_log = Path("/home/worker/service.log").open("wb")
        server = subprocess.Popen(["/usr/local/bin/opencode", "serve", "--hostname", "127.0.0.1", "--port", "4096"],
                                  cwd="/control", stdout=server_log, stderr=server_log, start_new_session=True)
        startup_deadline = min(context["deadline_epoch"], time.time() + 60)
        while True:
            if server.poll() is not None or time.time() >= startup_deadline:
                raise WorkerFailure("service_start_failed")
            baseline.password = service_password('/home/worker/service.log')
            if baseline.password is None:
                baseline.remaining()
                time.sleep(0.1)
                continue
            try:
                info = baseline.api("get", "/api/info")
                break
            except (WorkerFailure, json.JSONDecodeError):
                baseline.remaining()
                time.sleep(0.1)
        if info["version"] != context["profile"]["runtime"]["opencode_version"] or info["pid"] != server.pid:
            raise WorkerFailure("service_identity_mismatch")
        result["service"] = {"version": info["version"], "pid": info["pid"], "hostname": socket.gethostname(),
                             "uid": os.geteuid(), "location": "/control"}
        # Shell requests resolve configuration at /control, not inside the repository.
        commands = context["profile"]["commands"]
        work = [(f"setup-{index:02d}", "setup", entry) for index, entry in enumerate(commands["setup"], 1)]
        work += [(name, "check", entry) for name, entry in commands["checks"].items()]
        for name, stage, entry in work:
            check = baseline.command(name, stage, entry)
            result["checks"].append(check)
            if check["status"] != "exited" or check["exit"] != 0:
                raise WorkerFailure("required_command_failed")
        result["outcome"] = "passed"
        result["diagnostic"] = None
    except WorkerFailure as exc:
        result["diagnostic"] = str(exc)
    except subprocess.TimeoutExpired:
        result["diagnostic"] = "runtime_timeout"
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError):
        # Do not leak repository output, command arguments or raw exception strings.
        result["diagnostic"] = "bootstrap_failed"
    finally:
        if server is not None and server.poll() is None:
            os.killpg(server.pid, signal.SIGTERM)
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait()
        if server_log is not None:
            server_log.close()
        write_evidence(result)
    return 0 if result["outcome"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
