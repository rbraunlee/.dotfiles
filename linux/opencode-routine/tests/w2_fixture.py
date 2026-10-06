"""Reusable, disposable W2 fixtures; no OpenCode/service/project-command execution.

W2Fixture is deliberately not a TestCase and does not import historical tests.
Only fixture Git operations execute. FakeAdapter never launches sessions/processes.
"""
from collections import deque
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

PACKAGE = Path(__file__).resolve().parents[1]
LIBRARY = PACKAGE / ".local/lib/opencode-routine"
sys.path.insert(0, str(LIBRARY))

from routine.launcher import Launcher
from routine.store import Store


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


class FakeClock:
    """Epoch and monotonic clocks advance together, without real sleeping."""
    def __init__(self, epoch=1700000000.0, monotonic=100.0):
        self.epoch = float(epoch)
        self.ticks = float(monotonic)
        self.sleeps = []
        self._lock = threading.Lock()

    def time(self):
        with self._lock:
            return self.epoch

    def monotonic(self):
        with self._lock:
            return self.ticks

    def advance(self, seconds):
        if seconds < 0:
            raise ValueError("Fixture clock cannot move backwards")
        with self._lock:
            self.epoch += seconds
            self.ticks += seconds

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.advance(seconds)


class SimulatedCrash(BaseException):
    """Bypasses ordinary error handlers, modelling an interrupted lifecycle driver."""


class FakeAdapter:
    """Strict documented W2 adapter, configurable only by this test harness.

calls: ordered (method, copied keyword arguments). hooks[name](arguments) runs
after recording the call and before its fake result. responses[name] overrides
the normal result (value or callable); delays[name] advances the injected clock.
polls is a deque of exact poll records; its last item repeats until replaced.
No fake ID/PID represents a live session/process.
"""
    def __init__(self, clock=None):
        self.clock = clock or FakeClock()
        self.calls = []
        self.call_times = []
        self.hooks = {}
        self.responses = {}
        self.delays = {}
        self.polls = deque()
        self.sessions = []
        self.commands = []
        self.children = []
        self.unrelated = {"session": "user-session", "process": {"pid": 999999, "start_id": "user-owned"}}

    def _call(self, name, arguments, default):
        self.calls.append((name, deepcopy(arguments)))
        self.call_times.append(self.clock.monotonic())
        hook = self.hooks.get(name)
        if hook:
            hook(arguments)
        self.clock.advance(self.delays.get(name, 0))
        response = self.responses.get(name, default)
        if isinstance(response, BaseException):
            raise response
        return deepcopy(response(arguments) if callable(response) else response)

    def names(self):
        return [name for name, _ in self.calls]

    def arguments(self, name):
        return [arguments for method, arguments in self.calls if method == name]

    def qualify(self, *, directory, handoff, runtime, bundle_sha256, deadline, max_bytes):
        return self._call("qualify", locals_without_self(locals()), {
            "version": runtime["opencode_version"], "api_sha256": runtime["api_sha256"],
            "configuration_sha256": runtime["configuration_sha256"],
            "bundle_sha256": bundle_sha256, "directory": str(directory),
            "qualification": "deterministic", "roles_sha256": digest(b"fixture roles"),
            "discovery_sha256": digest(b"fixture discovery"), "permissions_verified": True,
            "stopping_verified": True, "delegation_verified": True})

    def create_session(self, *, directory, run_key, driver_id, deadline):
        record = {"id": f"ses_fixture_{len(self.sessions) + 1}", "directory": str(directory),
                  "parent_id": None, "owner": run_key}
        result = self._call("create_session", locals_without_self(locals(), "record"), record)
        self.sessions.append(deepcopy(result))
        return result

    def discover_children(self, *, session, directory, run_key, deadline, max_bytes):
        return self._call("discover_children", locals_without_self(locals()), self.children)

    def start_command(self, *, directory, session, argv, timeout_seconds, run_key, driver_id, deadline):
        record = {"id": f"sh_fixture_{len(self.commands) + 1}", "directory": str(directory),
                  "session_id": session["id"], "owner": run_key,
                  "processes": [{"pid": 900000 + len(self.commands), "start_id": "fixture-not-live"}]}
        result = self._call("start_command", locals_without_self(locals(), "record"), record)
        self.commands.append(deepcopy(result))
        return result

    def poll_command(self, *, command, deadline, max_bytes):
        default = self.polls[0] if self.polls else {"status": "exited", "exit": 0, "progress": True}
        if len(self.polls) > 1:
            self.polls.popleft()
        return self._call("poll_command", locals_without_self(locals(), "default"), default)

    def collect(self, *, sessions, commands, deadline, max_bytes):
        return self._call("collect", locals_without_self(locals()), {"diagnostics": []})

    def stop(self, *, directory, sessions, commands, run_key, driver_id, deadline, max_bytes):
        return self._call("stop", locals_without_self(locals()), {
            "confirmed": True, "sessions": [session["id"] for session in sessions],
            "commands": [command["id"] for command in commands],
            "descendants_stopped": True, "unrelated_preserved": True})


def locals_without_self(values, *exclude):
    return {key: value for key, value in values.items() if key not in ("self", *exclude)}


class W2Fixture:
    """Independent trusted project/home/state/bundle owned only by this fixture.

Use as a context manager or register close with addCleanup. Before authorize(),
edit profile and call save_profile(). approved()/claim() are W1-only operations;
claimed() yields a leased Coordinator and claimed run. prepare_routing_assets()
assembles two independent clones/canaries, never runtime qualification.
"""
    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="routine-w2-", dir="/tmp/opencode")
        self.base = Path(self.temporary.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.bundle = self.base / "bundle"
        contracts = {
            "orchestrator": "Own exactly one assigned slice; never claim another. Delegate only in its clone.",
            "builder": "Own implementation and tests only in the assigned clone. Do not edit launcher state.",
            "tester": "Independently verify; do not edit product code or committed tests. No scaffold mode.",
            "reviewer": "Fresh read-only review of approved criteria; no edits, state writes or commits.",
        }
        for role, contract in contracts.items():
            self.write_at(self.bundle / f"agents/{role}.md",
                          (f"# Disposable routing fixture: {role}\n{contract}\n"
                           "No GitHub, integration, service management, secrets or production access.\n").encode())
        self.write_at(self.bundle / "skills/tdd/SKILL.md", b"# Fixture contract\nBuilder owns test authoring.\n")
        self.write_at(self.bundle / "provenance.md", b"# Locally authored minimal disposable W2 contracts; not W3 qualification.\n")
        self.inventory = [{"path": path.relative_to(self.bundle).as_posix(), "sha256": digest(path.read_bytes())}
                          for path in sorted(self.bundle.rglob("*")) if path.is_file()]
        self.bundle_sha256 = digest(canonical(self.inventory))
        self.api = self.base / "reviewed-api.json"
        self.api.write_bytes(b'{"openapi":"3.1.0","info":{"version":"deterministic-fixture"}}\n')
        self.configuration = self.base / "reviewed-configuration.json"
        self.configuration.write_bytes(b'{"fixture":"offline identity only, not runtime configuration"}\n')
        self.git("init", "--initial-branch=main")
        self.write_at(self.root / "README.md", b"Disposable trusted W2 baseline.\n")
        self.write_at(self.root / "routing-canary.txt", b"original-checkout-canary\n")
        self.write_at(self.root / "fixture_commands.py",
                      b"# Inert fixture asset: tests use FakeAdapter, never execute this file.\n")
        self.git("add", "README.md", "routing-canary.txt", "fixture_commands.py")
        self.git("-c", "user.name=W2 Fixture", "-c", "user.email=w2@example.invalid",
                 "commit", "-m", "Disposable fixture baseline")
        self.commit = self.git("rev-parse", "HEAD").strip()
        self.profile = {
            "version": 4, "execution": "trusted-local", "commands": {"setup": [], "checks": {
                "test": {"argv": ["python3", "-B", "fixture_commands.py", "check"], "timeout_seconds": 30}}},
            "command_limits": {"command_seconds": 60, "input_bytes": 1048576, "output_bytes": 65536},
            "budgets": {"slice_seconds": 120, "inactivity_seconds": 5, "integration_seconds": 60, "repairs": 2},
            "concurrency": {"workers_per_feature": 3}, "credential_refs": ["fixture-model"],
            "runtime": {"opencode_version": "2.0.22", "api_sha256": digest(self.api.read_bytes()),
                        "configuration_sha256": digest(self.configuration.read_bytes()), "connection_ref": "fixture-service"},
            "services": [], "qa": {"kind": "none", "start": None}}
        spec = b"# Trusted fixture\n<!-- criterion: AC-1 -->\nOwner.\n<!-- criterion: AC-2 -->\nConsumer.\n"
        self.write_at(self.root / "planning/feature/spec.md", spec)
        tickets = []
        for slice_id, criteria, dependencies in (("01", ["AC-1"], []), ("02", ["AC-2"], ["01"]), ("03", ["AC-1"], [])):
            path = f"planning/feature/{slice_id}.md"
            data = f"# Fixture slice {slice_id}\nImplement mapped criteria only.\n".encode()
            self.write_at(self.root / path, data)
            tickets.append({"slice_id": slice_id, "path": path, "sha256": digest(data),
                            "criteria": criteria, "dependencies": dependencies})
        self.git("update-ref", "refs/heads/features/feature", self.commit)
        self.manifest = {"version": 2, "execution": "trusted-local", "feature_id": "feature",
                         "spec": {"path": "planning/feature/spec.md", "sha256": digest(spec), "criteria": ["AC-1", "AC-2"]},
                         "tickets": tickets, "profile_sha256": digest(canonical(self.profile)),
                         "bundle_sha256": self.bundle_sha256,
                         "baseline": {"commit": self.commit, "branch": "refs/heads/features/feature"}}
        self.evidence = {"version": 1, "execution": "trusted-local", "baseline": deepcopy(self.manifest["baseline"]),
                         "profile_sha256": self.manifest["profile_sha256"], "mutations_approved": True,
                         "checks": {"test": {"outcome": "passed", "evidence_ref": "approved-fixture-baseline"}}}
        self.save_profile()
        self.store = Store(self.base / "state")
        self.launcher = Launcher(self.store)
        self.authorization = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.temporary.cleanup()

    @staticmethod
    def write_at(path, data):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def env(self):
        return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.home / "config"), "XDG_DATA_HOME": str(self.home / "data"),
                "XDG_STATE_HOME": str(self.base / "cli-state"), "TMPDIR": "/tmp/opencode",
                "PYTHONPATH": str(LIBRARY), "PYTHONDONTWRITEBYTECODE": "1",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_TERMINAL_PROMPT": "0", "GIT_NO_REPLACE_OBJECTS": "1", "LC_ALL": "C"}

    def git(self, *args, cwd=None):
        result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *map(str, args)],
                                cwd=cwd or self.root, env=self.env(), capture_output=True,
                                text=True, check=True, timeout=10)
        return result.stdout

    def save_profile(self):
        data = canonical(self.profile)
        self.manifest["profile_sha256"] = digest(data)
        self.evidence["profile_sha256"] = digest(data)
        self.evidence["checks"] = {name: {"outcome": "passed", "evidence_ref": "approved-fixture-baseline"}
                                   for name in self.profile["commands"]["checks"]}
        self.write_at(self.root / ".opencode/routine/project.json", data)
        self.write_at(self.root / ".opencode/routine/features/feature/approval.json", canonical(self.manifest))

    def authorize(self):
        result = self.launcher.authorize_local("project", "feature", self.root, self.bundle,
                                               self.api, self.configuration, self.evidence)
        self.authorization = result["authorization_id"]
        return result

    def approved(self, slice_id="01", dispatch_id="dispatch-1"):
        authorization = self.authorization or self.authorize()["authorization_id"]
        self.launcher.authorize_local_dispatch("project", "feature", slice_id, dispatch_id, authorization)
        return authorization

    def claim(self, coordinator, slice_id="01", run_id="run-1", dispatch_id="dispatch-1"):
        authorization = self.approved(slice_id, dispatch_id)
        return coordinator.claim_local(slice_id, run_id, authorization, dispatch_id, self.manifest["baseline"])

    @contextmanager
    def claimed(self, slice_id="01", run_id="run-1", dispatch_id="dispatch-1"):
        self.approved(slice_id, dispatch_id)
        with self.launcher.coordinator("project", "feature", "coordinator") as coordinator:
            yield coordinator, self.claim(coordinator, slice_id, run_id, dispatch_id)["run"]

    def run(self, run_id="run-1"):
        return self.store.read()["runs"][f"project/{run_id}"]

    def feature(self):
        return self.store.read()["features"]["project/feature"]

    def mutate_ledger(self, mutation):
        """Explicit fixture-only fault injection under the production ledger lock."""
        with self.store.lock("ledger.lock"):
            ledger = self.store.read()
            mutation(ledger)
            self.store.write(ledger)

    def prepare_routing_assets(self):
        """Only independent Git clones and canaries; callers must obtain runtime approval."""
        clones = []
        template = self.base / "empty-template"
        template.mkdir(exist_ok=True)
        for name in ("routing-a", "routing-b"):
            clone = self.base / name
            self.git("clone", "--no-local", f"--template={template}", self.root, clone)
            self.git("checkout", "-b", f"fixture/{name}", self.commit, cwd=clone)
            (clone / "routing-canary.txt").write_text(name + "\n")
            clones.append(clone)
        return clones
