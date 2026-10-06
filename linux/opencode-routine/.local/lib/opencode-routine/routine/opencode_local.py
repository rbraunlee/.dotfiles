"""Bounded, explicitly injected OpenCode 2.0.22 adapter; never connects on its own.

Release sources (v2.0.22, not the moving published API):
  services/www/public/openapi.json
  packages/core/src/{shell.ts,session.ts,config.ts,config/discovery.ts}
  packages/core/src/tool/plugin/subagent.ts
  packages/server/src/handlers/{session.ts,shell.ts}

Transport is a callable (method, path, *, query, body, deadline, max_bytes)
returning response bytes. It must use the approved existing connection/auth context,
bound I/O and encode the supplied query keys literally (location[directory]).
No network client, subprocess, service discovery or service lifecycle is included.

Trusted assembly supplies reviewed API/configuration bytes and an offline discovery
callable. Discovery must inspect ALL release discovery inputs without loading them,
including well-known/explicit/inline inputs, variables, global and ancestor sources,
.opencode/.agents/.claude compatibility definitions and executable configuration.
It returns approved, directory, configuration_sha256, bundle_sha256,
discovery_sha256, entries_sha256 and roles_sha256. The last two identify canonical
API entries and resolved agents expected *before* any location is loaded.

Observer methods qualify, processes, delegation and stop provide visibility the
release API lacks. They receive deadline/max_bytes and must themselves bound work.
qualify returns the three exact verified booleans; processes returns exact process
identities (Linux PID/start ticks); delegation attests genuine delegated child IDs;
stop stops only supplied registered identities and returns the established stop
shape. Missing observations hold. Default qualification is deterministic; only
separately approved trusted real assembly may explicitly select 'real'.

The parent owns durable intent/identity/diagnostic journaling and fencing. In-memory
registries refuse arbitrary adoption and same-instance retries of ambiguous effects;
they are NOT crash recovery. Shell records/output are deliberately never deleted:
2.0.22 remove unlinks output and does not prove descendant termination. HTTP cancel,
interrupt acknowledgement and terminal parent status likewise are not stop proof.
"""
from copy import deepcopy
import math
import posixpath
import re
import shlex
import time

from .contracts import RoutineError, canonical, digest, parse_json


RELEASE_VERSION = "2.0.22"
RELEASE_API_SHA256 = "2bdc2b95f3a0f52a393ba76c0914151921d2ea33f91dbee17d29fa79e19e2620"
_FLAGS = {"permissions_verified", "stopping_verified", "delegation_verified"}
_STOP_KEYS = {"confirmed", "sessions", "commands", "descendants_stopped", "unrelated_preserved"}
_DIAGNOSTICS = ("command_failed", "command_timeout", "stop_uncertain", "output_omitted")
_MESSAGE = "Local runtime observations are unavailable or do not match approved inputs"


def _require(condition, code="local_hold"):
    if not condition:
        raise RoutineError(code, _MESSAGE)


def _hash(value):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value))
    return value


def _directory(value):
    _require(isinstance(value, str) and value.startswith("/") and not value.startswith("//")
             and "\x00" not in value and posixpath.normpath(value) == value)
    return value


def _id(value, prefix):
    _require(isinstance(value, str) and re.fullmatch(re.escape(prefix) + r"[A-Za-z0-9_-]{1,128}", value))
    return value


class _Budget:
    def __init__(self, maximum):
        _require(type(maximum) is int and maximum > 0)
        self.remaining = maximum

    def take(self, size):
        _require(size <= self.remaining)
        self.remaining -= size


class OpenCodeLocal:
    def __init__(self, transport=None, *, api_bytes=None, configuration_bytes=None,
                 discovery=None, observer=None, monotonic=time.monotonic,
                 max_bytes=1048576, max_pages=32, qualification="deterministic"):
        _require(type(max_bytes) is int and max_bytes > 0)
        _require(type(max_pages) is int and max_pages > 0)
        _require(qualification in ("deterministic", "real"))
        self.transport = transport
        self.api_bytes = api_bytes
        self.configuration_bytes = configuration_bytes
        self.discovery = discovery
        self.observer = observer
        self.monotonic = monotonic
        self.max_bytes = max_bytes
        self.max_pages = max_pages
        self.qualification = qualification
        self._qualified = {}
        self._sessions = {}
        self._commands = {}
        self._drivers = {}
        self._session_intents = {}
        self._command_intents = {}
        self._command_timeouts = {}
        self._command_deadlines = {}
        self._command_status = {}
        self._command_hashes = {}
        self._terminal_results = {}
        self._held_runs = set()

    def _time(self, deadline):
        _require(type(deadline) in (int, float) and math.isfinite(deadline))
        _require(self.monotonic() < deadline, "local_timeout")

    def _budget(self, maximum=None):
        if maximum is None:
            maximum = self.max_bytes
        _require(type(maximum) is int and maximum > 0)
        return _Budget(min(maximum, self.max_bytes))

    def _invoke(self, function, *, deadline, budget, **kwargs):
        self._time(deadline)
        _require(callable(function))
        try:
            result = function(deadline=deadline, max_bytes=budget.remaining, **deepcopy(kwargs))
            self._time(deadline)
            budget.take(len(canonical(result)))
            return deepcopy(result)
        except RoutineError:
            raise RoutineError("local_hold", _MESSAGE) from None
        except Exception:
            raise RoutineError("local_hold", _MESSAGE) from None

    def _observe(self, method, *, deadline, budget, **kwargs):
        try:
            function = getattr(self.observer, method, None)
        except Exception:
            raise RoutineError("local_hold", _MESSAGE) from None
        return self._invoke(function, deadline=deadline, budget=budget, **kwargs)

    def _request(self, method, path, *, query=None, body=None, deadline, budget, raw=False):
        self._time(deadline)
        _require(callable(self.transport) and budget.remaining > 0)
        try:
            # Bound requests as well as responses; secrets never enter diagnostics.
            budget.take(len(canonical({"query": query or {}, "body": body})))
            _require(budget.remaining > 0)
            result = self.transport(method, path, query=query or {}, body=body,
                                    deadline=deadline, max_bytes=budget.remaining)
            self._time(deadline)
            _require(isinstance(result, bytes))
            budget.take(len(result))
            return result if raw else parse_json(result)
        except RoutineError as exc:
            code = "local_timeout" if exc.code == "local_timeout" else "local_hold"
            raise RoutineError(code, _MESSAGE) from None
        except Exception:
            raise RoutineError("local_hold", _MESSAGE) from None

    @staticmethod
    def _location(directory):
        return {"location[directory]": directory}

    def qualify(self, *, directory, handoff, runtime, bundle_sha256, deadline, max_bytes):
        directory = _directory(directory)
        self._qualified.pop(directory, None)
        budget = self._budget(max_bytes)
        self._time(deadline)
        _hash(bundle_sha256)
        _require(isinstance(runtime, dict) and set(runtime) == {
            "opencode_version", "api_sha256", "configuration_sha256", "connection_ref"})
        _require(runtime["opencode_version"] == RELEASE_VERSION)
        _require(isinstance(self.api_bytes, bytes) and digest(self.api_bytes) == RELEASE_API_SHA256)
        _require(runtime["api_sha256"] == RELEASE_API_SHA256)
        _require(isinstance(self.configuration_bytes, bytes)
                 and digest(self.configuration_bytes) == runtime["configuration_sha256"])
        _require(len(self.api_bytes) + len(self.configuration_bytes) <= budget.remaining)
        _require(isinstance(handoff, dict) and set(handoff) == {"path", "sha256", "inventory"})
        _directory(handoff["path"])
        _hash(handoff["sha256"])
        _require(isinstance(handoff["inventory"], list))
        discovery = self._invoke(self.discovery, directory=directory, handoff=handoff,
                                 runtime=runtime, bundle_sha256=bundle_sha256,
                                 configuration_bytes=self.configuration_bytes,
                                 deadline=deadline, budget=budget)
        _require(isinstance(discovery, dict) and set(discovery) == {
            "approved", "directory", "configuration_sha256", "bundle_sha256",
            "discovery_sha256", "entries_sha256", "roles_sha256"})
        _require(discovery["approved"] is True and discovery["directory"] == directory
                 and discovery["configuration_sha256"] == runtime["configuration_sha256"]
                 and discovery["bundle_sha256"] == bundle_sha256)
        for key in ("discovery_sha256", "entries_sha256", "roles_sha256"):
            _hash(discovery[key])
        api = self._request("GET", "/openapi.json", deadline=deadline, budget=budget, raw=True)
        _require(digest(api) == RELEASE_API_SHA256)
        info = self._request("GET", "/api/info", deadline=deadline, budget=budget)
        _require(isinstance(info, dict) and info.get("version") == RELEASE_VERSION)
        query = self._location(directory)
        location = self._request("GET", "/api/location", query=query, deadline=deadline, budget=budget)
        _require(isinstance(location, dict) and location.get("directory") == directory)
        entries = self._request("GET", "/api/config", query=query, deadline=deadline, budget=budget)
        _require(isinstance(entries, list) and digest(canonical(entries)) == discovery["entries_sha256"])
        roles = self._request("GET", "/api/agent", query=query, deadline=deadline, budget=budget)
        _require(isinstance(roles, dict) and roles.get("location") == {"directory": directory}
                 and isinstance(roles.get("data"), list)
                 and digest(canonical(roles["data"])) == discovery["roles_sha256"])
        flags = self._observe("qualify", directory=directory, handoff=handoff, runtime=runtime,
                              bundle_sha256=bundle_sha256, discovery=discovery, location=location,
                              configuration=entries, roles=roles["data"], deadline=deadline, budget=budget)
        _require(isinstance(flags, dict) and set(flags) == _FLAGS
                 and all(flags[key] is True for key in _FLAGS))
        result = {"version": RELEASE_VERSION, "api_sha256": RELEASE_API_SHA256,
                  "configuration_sha256": runtime["configuration_sha256"],
                  "bundle_sha256": bundle_sha256, "directory": directory,
                  "qualification": self.qualification, "roles_sha256": discovery["roles_sha256"],
                  "discovery_sha256": discovery["discovery_sha256"], **flags}
        self._time(deadline)
        self._qualified[directory] = deepcopy(result)
        return result

    def _owner(self, directory, run_key, driver_id=None, *, stopping=False):
        _directory(directory)
        _require(isinstance(run_key, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/_-]{0,191}", run_key))
        if stopping:
            _require(run_key in self._drivers)
        else:
            _require(directory in self._qualified and run_key not in self._held_runs)
        if driver_id is not None:
            _require(isinstance(driver_id, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", driver_id))
            _require(run_key not in self._drivers or self._drivers[run_key] == driver_id)

    def _session(self, value):
        _require(isinstance(value, dict) and set(value) == {"id", "directory", "parent_id", "owner"})
        _id(value["id"], "ses")
        _require(value == self._sessions.get(value["id"]))
        return value

    def _command(self, value):
        _require(isinstance(value, dict) and set(value) == {
            "id", "directory", "session_id", "owner", "processes"})
        _id(value["id"], "sh_")
        _require(value == self._commands.get(value["id"]))
        return value

    def _session_record(self, info, *, directory, run_key, driver_id, parent_id):
        _require(isinstance(info, dict) and info.get("location") == {"directory": directory}
                 and info.get("parentID") == parent_id and "fork" not in info)
        metadata = info.get("metadata")
        _require(isinstance(metadata, dict) and metadata.get("routine_run_key") == run_key
                 and metadata.get("routine_driver_id") == driver_id)
        return {"id": _id(info.get("id"), "ses"), "directory": directory,
                "parent_id": parent_id, "owner": run_key}

    def create_session(self, *, directory, run_key, driver_id, deadline):
        self._time(deadline)
        self._owner(directory, run_key, driver_id)
        if run_key in self._session_intents:
            record = self._session_intents[run_key]
            _require(record is not None and record["directory"] == directory, "local_ambiguous")
            return deepcopy(record)
        self._drivers[run_key] = driver_id
        self._session_intents[run_key] = None
        try:
            result = self._request("POST", "/api/session", body={
                "location": {"directory": directory},
                "metadata": {"routine_run_key": run_key, "routine_driver_id": driver_id}},
                deadline=deadline, budget=self._budget())
            _require(isinstance(result, dict) and set(result) == {"data"})
            record = self._session_record(result["data"], directory=directory, run_key=run_key,
                                           driver_id=driver_id, parent_id=None)
            _require(record["id"] not in self._sessions)
            self._time(deadline)
        except Exception:
            self._held_runs.add(run_key)
            raise RoutineError("local_ambiguous", _MESSAGE) from None
        self._sessions[record["id"]] = deepcopy(record)
        self._session_intents[run_key] = deepcopy(record)
        return record

    def discover_children(self, *, session, directory, run_key, deadline, max_bytes):
        self._owner(directory, run_key)
        self._session(session)
        _require(session["owner"] == run_key and session["directory"] == directory)
        budget = self._budget(max_bytes)
        driver_id = self._drivers[run_key]
        # Discovery failures may leave real, unregistered descendants. Never turn
        # a partial traversal into a parent-only stopped/qualified success.
        self._held_runs.add(run_key)
        pending, records, seen = [session["id"]], [], {session["id"]}
        pages = 0
        while pending:
            parent = pending.pop(0)
            cursor, cursors = None, set()
            while True:
                pages += 1
                _require(pages <= self.max_pages)
                query = {"parentID": parent, "directory": directory, "limit": "50"}
                if cursor is not None:
                    query["cursor"] = cursor
                result = self._request("GET", "/api/session", query=query, deadline=deadline, budget=budget)
                _require(isinstance(result, dict) and set(result) == {"data", "cursor"}
                         and isinstance(result["data"], list) and len(result["data"]) <= 50
                         and isinstance(result["cursor"], dict))
                for info in result["data"]:
                    record = self._session_record(info, directory=directory, run_key=run_key,
                                                   driver_id=driver_id, parent_id=parent)
                    _require(record["id"] not in seen)
                    _require(record["id"] not in self._sessions or self._sessions[record["id"]] == record)
                    seen.add(record["id"])
                    pending.append(record["id"])
                    records.append(record)
                cursor = result["cursor"].get("next")
                if cursor is None:
                    break
                _require(isinstance(cursor, str) and cursor and len(cursor) <= 4096 and cursor not in cursors)
                cursors.add(cursor)
        if records:
            delegated = self._observe("delegation", parent=session, sessions=records,
                                      deadline=deadline, budget=budget)
            _require(isinstance(delegated, list) and len(delegated) == len(records)
                     and all(isinstance(item, str) for item in delegated)
                     and set(delegated) == {record["id"] for record in records})
        self._time(deadline)
        for record in records:
            self._sessions[record["id"]] = deepcopy(record)
        self._held_runs.discard(run_key)
        return records

    @staticmethod
    def _shell(result, command):
        _require(isinstance(result, dict) and set(result) == {"location", "data"}
                 and result["location"] == {"directory": command["directory"]})
        info = result["data"]
        _require(isinstance(info, dict) and info.get("id") == command["id"]
                 and info.get("cwd") == command["directory"])
        metadata = info.get("metadata")
        _require(isinstance(metadata, dict) and metadata.get("routine_run_key") == command["owner"]
                 and metadata.get("routine_session_id") == command["session_id"])
        _require(info.get("status") in ("running", "exited", "timeout", "killed"))
        exit_code = info.get("exit")
        _require(exit_code is None or type(exit_code) is int)
        _require(info["status"] != "exited" or exit_code is not None)
        return info

    def start_command(self, *, directory, session, argv, timeout_seconds, run_key, driver_id, deadline):
        self._time(deadline)
        self._owner(directory, run_key, driver_id)
        self._session(session)
        _require(session["owner"] == run_key and session["directory"] == directory)
        _require(isinstance(argv, list) and argv and all(isinstance(arg, str) and "\x00" not in arg for arg in argv)
                 and argv[0])
        _require(type(timeout_seconds) is int and timeout_seconds > 0)
        budget = self._budget()
        quoted = shlex.join(argv)
        key = (run_key, session["id"], digest(canonical(argv)))
        if key in self._command_intents:
            record = self._command_intents[key]
            _require(record is not None and self._command_timeouts[key] == timeout_seconds,
                     "local_ambiguous")
            return deepcopy(record)
        started = self.monotonic()
        timeout_ms = min(timeout_seconds * 1000, math.floor((deadline - started) * 1000))
        # Release uses Duration.millis; zero disables timeout, so never send zero.
        _require(timeout_ms > 0, "local_timeout")
        self._command_intents[key] = None
        self._command_timeouts[key] = timeout_seconds
        expires = started + timeout_ms / 1000
        try:
            result = self._request("POST", "/api/shell", query=self._location(directory), body={
                "command": quoted, "cwd": directory, "timeout": timeout_ms,
                "metadata": {"routine_run_key": run_key, "routine_driver_id": driver_id,
                             "routine_session_id": session["id"]}}, deadline=deadline, budget=budget)
            _require(isinstance(result, dict) and isinstance(result.get("data"), dict))
            record = {"id": _id(result["data"].get("id"), "sh_"), "directory": directory,
                      "session_id": session["id"], "owner": run_key, "processes": []}
            info = self._shell(result, record)
            _require(info.get("command") == quoted)
            _require(info["metadata"].get("routine_driver_id") == driver_id)
            _require(record["id"] not in self._commands)
            processes = self._observe("processes", command=record, info=info, deadline=deadline, budget=budget)
            _require(isinstance(processes, list) and processes)
            identities = set()
            for process in processes:
                _require(isinstance(process, dict) and set(process) == {"pid", "start_id"}
                         and type(process["pid"]) is int and process["pid"] > 0
                         and isinstance(process["start_id"], str)
                         and re.fullmatch(r"[0-9]{1,32}", process["start_id"]))
                identity = (process["pid"], process["start_id"])
                _require(identity not in identities)
                identities.add(identity)
            _require(type(info.get("pid")) is int and any(p["pid"] == info["pid"] for p in processes))
            record["processes"] = processes
            self._time(deadline)
            _require(self.monotonic() < expires)
        except Exception:
            self._held_runs.add(run_key)
            raise RoutineError("local_ambiguous", _MESSAGE) from None
        self._commands[record["id"]] = deepcopy(record)
        self._command_intents[key] = deepcopy(record)
        self._command_deadlines[record["id"]] = expires
        self._command_status[record["id"]] = info["status"]
        self._command_hashes[record["id"]] = digest(canonical(quoted))
        return record

    def _poll(self, command, *, deadline, budget):
        self._time(deadline)
        self._command(command)
        result = self._request("GET", "/api/shell/" + command["id"],
                               query=self._location(command["directory"]), deadline=deadline, budget=budget)
        info = self._shell(result, command)
        _require(isinstance(info.get("command"), str)
                 and digest(canonical(info["command"])) == self._command_hashes[command["id"]])
        _require(info["metadata"].get("routine_driver_id") == self._drivers[command["owner"]])
        status = info["status"]
        if command["id"] in self._terminal_results:
            observed = self._terminal_results[command["id"]]
            _require(status == observed["status"] and info.get("exit") == observed["exit"])
            return dict(observed, progress=False)
        if self.monotonic() >= self._command_deadlines[command["id"]] and status in ("running", "exited"):
            return {"status": "timeout", "exit": None, "progress": False}
        progress = status != self._command_status[command["id"]]
        self._command_status[command["id"]] = status
        observed = {"status": status, "exit": info.get("exit"), "progress": progress}
        if status != "running":
            self._terminal_results[command["id"]] = deepcopy(observed)
        return observed

    def poll_command(self, *, command, deadline, max_bytes):
        return self._poll(command, deadline=deadline, budget=self._budget(max_bytes))

    def _sets(self, sessions, commands):
        _require(isinstance(sessions, list) and isinstance(commands, list))
        for session in sessions:
            self._session(session)
        for command in commands:
            self._command(command)
        _require(len({s["id"] for s in sessions}) == len(sessions)
                 and len({c["id"] for c in commands}) == len(commands))

    def collect(self, *, sessions, commands, deadline, max_bytes):
        self._sets(sessions, commands)
        self._time(deadline)
        budget = self._budget(max_bytes)
        counts = {code: 0 for code in _DIAGNOSTICS}
        for command in commands:
            result = self._poll(command, deadline=deadline, budget=budget)
            if result["status"] == "killed" or (result["status"] == "exited" and result["exit"] != 0):
                counts["command_failed"] += 1
            if result["status"] == "timeout":
                counts["command_timeout"] += 1
            counts["output_omitted"] += 1
        result = {"diagnostics": [{"code": code, "count": count} for code, count in counts.items() if count]}
        budget.take(len(canonical(result)))
        self._time(deadline)
        return result

    def stop(self, *, directory, sessions, commands, run_key, driver_id, deadline, max_bytes):
        self._time(deadline)
        self._owner(directory, run_key, driver_id, stopping=True)
        self._sets(sessions, commands)
        _require(all(s["owner"] == run_key and s["directory"] == directory for s in sessions)
                 and all(c["owner"] == run_key and c["directory"] == directory for c in commands))
        session_ids = [s["id"] for s in sessions]
        command_ids = [c["id"] for c in commands]
        _require(set(session_ids) == {s["id"] for s in self._sessions.values() if s["owner"] == run_key}
                 and set(command_ids) == {c["id"] for c in self._commands.values() if c["owner"] == run_key})
        result = {"confirmed": False, "sessions": session_ids, "commands": command_ids,
                  "descendants_stopped": False, "unrelated_preserved": False}
        budget = self._budget(max_bytes)
        try:
            # Interrupt children before parents. Never delete sessions or shell output.
            for session in reversed(sessions):
                ack = self._request("POST", "/api/session/" + session["id"] + "/interrupt",
                                    query={"resume": "false"}, deadline=deadline, budget=budget)
                _require(isinstance(ack, dict) and set(ack) == {"interrupted"}
                         and type(ack["interrupted"]) is bool)
            observed = self._observe("stop", directory=directory, sessions=sessions, commands=commands,
                                     run_key=run_key, driver_id=driver_id, deadline=deadline, budget=budget)
            _require(isinstance(observed, dict) and set(observed) == _STOP_KEYS
                     and isinstance(observed["sessions"], list) and isinstance(observed["commands"], list)
                     and len(observed["sessions"]) == len(session_ids)
                     and len(observed["commands"]) == len(command_ids)
                     and set(observed["sessions"]) == set(session_ids)
                     and set(observed["commands"]) == set(command_ids)
                     and all(observed[key] is True for key in (
                         "confirmed", "descendants_stopped", "unrelated_preserved")))
            self._time(deadline)
            _require(run_key not in self._held_runs)
            result.update(confirmed=True, descendants_stopped=True, unrelated_preserved=True)
        except Exception:
            # Cancellation/late response/missing visibility never proves stopped work.
            pass
        return result
