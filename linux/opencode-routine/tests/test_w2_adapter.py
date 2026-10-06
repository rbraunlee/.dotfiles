"""Builder-owned release adapter contracts; no real service or process execution."""
from copy import deepcopy
import json
from pathlib import Path
import shlex
import sys
import unittest
from unittest.mock import patch

LIBRARY = Path(__file__).resolve().parents[1] / ".local/lib/opencode-routine"
sys.path.insert(0, str(LIBRARY))

from routine.contracts import RoutineError, canonical, digest
from routine.opencode_local import OpenCodeLocal, RELEASE_API_SHA256


DIRECTORY = "/tmp/opencode/adapter-checkout"
API = b'{"offline":"release-contract-test"}'
ENTRIES = [{"type": "document", "path": "/approved/opencode.jsonc",
            "info": {"plugins": [], "providers": {"secret": "SECRET_CONFIG"}}}]
CONFIGURATION = canonical(ENTRIES)
ROLES = [{"id": "builder", "mode": "subagent", "permissions": []}]
RUNTIME = {"opencode_version": "2.0.22", "api_sha256": digest(API),
           "configuration_sha256": digest(CONFIGURATION), "connection_ref": "approved-service"}
BUNDLE = "b" * 64
HANDOFF = {"path": "/tmp/opencode/handoff", "sha256": "a" * 64, "inventory": []}


class Clock:
    def __init__(self):
        self.now = 10.0

    def __call__(self):
        return self.now


def session_info(sid="ses_parent", parent=None):
    result = {"id": sid, "location": {"directory": DIRECTORY},
              "metadata": {"routine_run_key": "project/run", "routine_driver_id": "driver"},
              "title": "SECRET_TITLE"}
    if parent:
        result["parentID"] = parent
    return result


def shell_info(status="running", exit=None):
    result = {"id": "sh_owned", "status": status, "cwd": DIRECTORY,
              "command": shlex.join(["printf", "%s", "literal; $(secret)\nwith 'quote'"]),
              "file": "SECRET_PATH", "pid": 456,
              "time": {"started": 10000},
              "metadata": {"routine_run_key": "project/run", "routine_driver_id": "driver",
                           "routine_session_id": "ses_parent"}}
    if exit is not None:
        result["exit"] = exit
    return result


class Transport:
    def __init__(self):
        self.calls = []
        self.responses = {}
        self.pages = []
        self.hook = None
        self.command_text = "SECRET_COMMAND"

    def __call__(self, method, path, *, query, body, deadline, max_bytes):
        self.calls.append((method, path, deepcopy(query), deepcopy(body), deadline, max_bytes))
        if self.hook:
            self.hook(method, path)
        key = (method, path)
        if key in self.responses:
            value = self.responses[key]
            if isinstance(value, Exception):
                raise value
            return value if isinstance(value, bytes) else canonical(value)
        if path == "/openapi.json":
            return API
        if path == "/api/info":
            return canonical({"version": "2.0.22"})
        if path == "/api/config":
            return canonical(ENTRIES)
        if path == "/api/location":
            return canonical({"directory": DIRECTORY, "project": {"id": "shared-project"}})
        if path == "/api/agent":
            return canonical({"location": {"directory": DIRECTORY}, "data": ROLES})
        if path == "/api/session" and method == "POST":
            return canonical({"data": session_info()})
        if path == "/api/session" and method == "GET":
            return canonical(self.pages.pop(0) if self.pages else {"data": [], "cursor": {"next": None}})
        if path.endswith("/interrupt"):
            return canonical({"interrupted": True})
        if path == "/api/shell" and method == "POST":
            self.command_text = body["command"]
            info = shell_info()
            info["command"] = self.command_text
            return canonical({"location": {"directory": DIRECTORY}, "data": info})
        if path == "/api/shell/sh_owned":
            info = shell_info("exited", 0)
            info["command"] = self.command_text
            return canonical({"location": {"directory": DIRECTORY}, "data": info})
        raise AssertionError("Unexpected offline fixture request")


class Observer:
    def __init__(self):
        self.flags = {"permissions_verified": True, "stopping_verified": True,
                      "delegation_verified": True}
        self.identities = [{"pid": 456, "start_id": "987654"}]
        self.stop_confirmed = True
        self.delegated = None
        self.calls = []

    def qualify(self, **kwargs):
        self.calls.append(("qualify", kwargs))
        return deepcopy(self.flags)

    def processes(self, **kwargs):
        self.calls.append(("processes", kwargs))
        return deepcopy(self.identities)

    def delegation(self, **kwargs):
        self.calls.append(("delegation", kwargs))
        return self.delegated if self.delegated is not None else [s["id"] for s in kwargs["sessions"]]

    def stop(self, **kwargs):
        self.calls.append(("stop", kwargs))
        return {"confirmed": self.stop_confirmed,
                "sessions": [s["id"] for s in kwargs["sessions"]],
                "commands": [c["id"] for c in kwargs["commands"]],
                "descendants_stopped": self.stop_confirmed, "unrelated_preserved": self.stop_confirmed}


class AdapterTests(unittest.TestCase):
    def setUp(self):
        # Small synthetic bytes exercise identity mechanics, never release qualification.
        self.release_patch = patch("routine.opencode_local.RELEASE_API_SHA256", digest(API))
        self.release_patch.start()
        self.addCleanup(self.release_patch.stop)
        self.clock = Clock()
        self.transport = Transport()
        self.observer = Observer()
        self.discovery_calls = []
        self.discovery_result = {"approved": True, "directory": DIRECTORY,
                                 "configuration_sha256": digest(CONFIGURATION),
                                 "bundle_sha256": BUNDLE, "discovery_sha256": "d" * 64,
                                 "entries_sha256": digest(canonical(ENTRIES)),
                                 "roles_sha256": digest(canonical(ROLES))}
        self.adapter = self.make_adapter()

    def discovery(self, **kwargs):
        self.discovery_calls.append(kwargs)
        self.assertEqual(self.transport.calls, [])
        return deepcopy(self.discovery_result)

    def make_adapter(self, **kwargs):
        values = dict(transport=self.transport, api_bytes=API, configuration_bytes=CONFIGURATION,
                      discovery=self.discovery, observer=self.observer, monotonic=self.clock)
        values.update(kwargs)
        return OpenCodeLocal(**values)

    def qualify(self, adapter=None, **kwargs):
        values = dict(directory=DIRECTORY, handoff=HANDOFF, runtime=RUNTIME,
                      bundle_sha256=BUNDLE, deadline=100.0, max_bytes=65536)
        values.update(kwargs)
        return (adapter or self.adapter).qualify(**values)

    def create(self, adapter=None, **kwargs):
        values = dict(directory=DIRECTORY, run_key="project/run", driver_id="driver", deadline=100.0)
        values.update(kwargs)
        return (adapter or self.adapter).create_session(**values)

    def start(self, session=None, **kwargs):
        values = dict(directory=DIRECTORY, session=session or self.create(),
                      argv=["printf", "%s", "literal; $(secret)\nwith 'quote'"],
                      timeout_seconds=7, run_key="project/run", driver_id="driver", deadline=100.0)
        values.update(kwargs)
        return self.adapter.start_command(**values)

    def stop(self, sessions, commands, **kwargs):
        values = dict(directory=DIRECTORY, sessions=sessions, commands=commands, run_key="project/run",
                      driver_id="driver", deadline=100.0, max_bytes=65536)
        values.update(kwargs)
        return self.adapter.stop(**values)

    def reject(self, operation):
        with self.assertRaises(RoutineError) as cm:
            operation()
        self.assertNotIn("SECRET", str(cm.exception))
        return cm.exception

    def test_pinned_authoritative_release_hash(self):
        self.assertEqual(RELEASE_API_SHA256,
                         "2bdc2b95f3a0f52a393ba76c0914151921d2ea33f91dbee17d29fa79e19e2620")

    def test_constructor_is_inert_and_default_fails_closed(self):
        self.assertEqual(self.transport.calls, [])
        self.reject(lambda: self.qualify(OpenCodeLocal()))
        self.assertEqual(self.transport.calls, [])

    def test_offline_gate_is_before_any_location_configuration_request(self):
        self.discovery_result["approved"] = False
        self.reject(self.qualify)
        self.assertEqual(self.transport.calls, [])

    def test_missing_offline_gate_fails_closed(self):
        self.reject(lambda: self.qualify(self.make_adapter(discovery=None)))
        self.assertEqual(self.transport.calls, [])

    def test_offline_gate_binds_directory_bundle_configuration(self):
        for key in ("directory", "bundle_sha256", "configuration_sha256"):
            with self.subTest(key=key):
                old = self.discovery_result[key]
                self.discovery_result[key] = "mismatch"
                self.reject(self.qualify)
                self.assertEqual(self.transport.calls, [])
                self.discovery_result[key] = old

    def test_qualification_exact_safe_shape_and_deep_object_location(self):
        result = self.qualify()
        self.assertEqual(set(result), {"version", "api_sha256", "configuration_sha256", "bundle_sha256",
                                      "directory", "qualification", "roles_sha256", "discovery_sha256",
                                      "permissions_verified", "stopping_verified", "delegation_verified"})
        self.assertEqual(result["version"], "2.0.22")
        self.assertEqual(result["qualification"], "deterministic")
        self.assertNotIn("SECRET", json.dumps(result))
        for _, path, query, _, deadline, cap in self.transport.calls:
            if path in ("/api/config", "/api/location", "/api/agent"):
                self.assertEqual(query, {"location[directory]": DIRECTORY})
            self.assertEqual(deadline, 100)
            self.assertGreater(cap, 0)

    def test_release_api_configuration_mismatch_no_create(self):
        cases = [("/openapi.json", b'{"current":"different"}'),
                 ("/api/info", {"version": "2.0.23"}),
                 ("/api/config", [{"type": "document", "info": {"plugins": ["SECRET_PLUGIN"]}}]),
                 ("/api/agent", {"location": {"directory": DIRECTORY}, "data": []}),
                 ("/api/location", {"directory": "/unrelated"})]
        for path, value in cases:
            with self.subTest(path=path):
                self.transport.calls.clear()
                self.transport.responses = {("GET", path): value}
                self.reject(self.qualify)
                self.reject(self.create)
                self.assertFalse(any(c[0] == "POST" for c in self.transport.calls))

    def test_runtime_inputs_must_match_reviewed_bytes(self):
        for key in ("opencode_version", "api_sha256", "configuration_sha256"):
            value = dict(RUNTIME, **{key: "changed"})
            self.reject(lambda: self.qualify(runtime=value))
            self.assertEqual(self.transport.calls, [])

    def test_missing_observations_fail_closed(self):
        for flag in self.observer.flags:
            self.transport.calls.clear()
            self.observer.flags[flag] = False
            self.reject(self.qualify)
            self.reject(self.create)
            self.observer.flags[flag] = True

    def test_no_observer_is_not_permission_delegation_or_stop_proof(self):
        self.reject(lambda: self.qualify(self.make_adapter(observer=None)))

    def test_create_explicit_location_metadata_and_exact_record(self):
        self.qualify()
        result = self.create()
        self.assertEqual(result, {"id": "ses_parent", "directory": DIRECTORY,
                                  "parent_id": None, "owner": "project/run"})
        request = self.transport.calls[-1]
        self.assertEqual(request[:3], ("POST", "/api/session", {}))
        self.assertEqual(request[3], {"location": {"directory": DIRECTORY},
                                     "metadata": {"routine_run_key": "project/run",
                                                  "routine_driver_id": "driver"}})
        self.assertNotIn("SECRET", json.dumps(result))

    def test_create_without_qualification_or_other_directory_is_refused(self):
        self.reject(self.create)
        self.qualify()
        self.reject(lambda: self.create(directory="/other"))
        self.assertFalse(any(c[0] == "POST" for c in self.transport.calls))

    def test_ambiguous_create_is_not_retried(self):
        self.qualify()
        self.transport.responses[("POST", "/api/session")] = TimeoutError("SECRET_AUTH")
        self.reject(self.create)
        self.reject(self.create)
        self.assertEqual(sum(c[:2] == ("POST", "/api/session") for c in self.transport.calls), 1)

    def test_duplicate_success_create_does_not_launch_again(self):
        self.qualify()
        result = self.create()
        self.assertEqual(self.create(), result)
        self.assertEqual(sum(c[:2] == ("POST", "/api/session") for c in self.transport.calls), 1)

    def test_create_wrong_location_or_owner_is_ambiguous(self):
        for field in ("location", "metadata"):
            self.transport.calls.clear()
            adapter = self.make_adapter()
            self.qualify(adapter)
            value = session_info()
            value[field] = {"directory": "/other"} if field == "location" else {}
            self.transport.responses[("POST", "/api/session")] = {"data": value}
            self.reject(lambda: self.create(adapter))
            self.reject(lambda: self.create(adapter))
            self.assertEqual(sum(c[:2] == ("POST", "/api/session") for c in self.transport.calls), 1)

    def test_children_use_owned_parent_links_and_bounded_pagination(self):
        self.qualify()
        root = self.create()
        self.transport.pages = [
            {"data": [session_info("ses_child", root["id"])], "cursor": {"next": "page2"}},
            {"data": [], "cursor": {"next": None}},
            {"data": [session_info("ses_grandchild", "ses_child")], "cursor": {"next": None}},
            {"data": [], "cursor": {"next": None}}]
        result = self.adapter.discover_children(session=root, directory=DIRECTORY, run_key="project/run",
                                                deadline=100, max_bytes=65536)
        self.assertEqual([s["id"] for s in result], ["ses_child", "ses_grandchild"])
        lists = [c for c in self.transport.calls if c[:2] == ("GET", "/api/session")]
        self.assertEqual(lists[0][2], {"parentID": "ses_parent", "directory": DIRECTORY, "limit": "50"})
        self.assertEqual(lists[1][2]["cursor"], "page2")
        self.assertTrue(all(s["owner"] == "project/run" for s in result))

    def test_unrelated_fork_wrong_directory_and_missing_genuine_delegation_hold(self):
        self.qualify()
        root = self.create()
        for mutation in ("parent", "directory", "owner", "fork", "delegation"):
            child = session_info("ses_child", root["id"])
            self.observer.delegated = None
            if mutation == "parent":
                child["parentID"] = "ses_unrelated"
            elif mutation == "directory":
                child["location"]["directory"] = "/other"
            elif mutation == "owner":
                child["metadata"] = {}
            elif mutation == "fork":
                child["fork"] = {"sessionID": root["id"]}
            else:
                self.observer.delegated = []
            self.transport.pages = [{"data": [child], "cursor": {"next": None}}]
            self.reject(lambda: self.adapter.discover_children(session=root, directory=DIRECTORY,
                         run_key="project/run", deadline=100, max_bytes=65536))

    def test_pagination_cycles_and_page_limits_hold(self):
        self.qualify()
        root = self.create()
        self.transport.pages = [{"data": [], "cursor": {"next": "same"}}] * 3
        self.reject(lambda: self.adapter.discover_children(session=root, directory=DIRECTORY,
                    run_key="project/run", deadline=100, max_bytes=65536))

    def test_command_quoted_argv_cwd_deep_object_and_millisecond_timeout(self):
        self.qualify()
        result = self.start()
        self.assertEqual(result, {"id": "sh_owned", "directory": DIRECTORY, "session_id": "ses_parent",
                                  "owner": "project/run", "processes": [{"pid": 456, "start_id": "987654"}]})
        request = self.transport.calls[-1]
        self.assertEqual(request[:3], ("POST", "/api/shell", {"location[directory]": DIRECTORY}))
        self.assertEqual(request[3]["cwd"], DIRECTORY)
        self.assertEqual(request[3]["timeout"], 7000)
        self.assertEqual(shlex.split(request[3]["command"]),
                         ["printf", "%s", "literal; $(secret)\nwith 'quote'"])
        self.assertNotIn("SECRET", json.dumps(result))

    def test_no_process_start_identity_is_ambiguous_not_retried(self):
        self.qualify()
        root = self.create()
        self.observer.identities = []
        self.reject(lambda: self.start(root))
        self.reject(lambda: self.start(root))
        self.assertEqual(sum(c[:2] == ("POST", "/api/shell") for c in self.transport.calls), 1)

    def test_ambiguous_command_is_not_retried(self):
        self.qualify()
        root = self.create()
        self.transport.responses[("POST", "/api/shell")] = OSError("SECRET_AUTH")
        self.reject(lambda: self.start(root))
        self.reject(lambda: self.start(root))
        self.assertEqual(sum(c[:2] == ("POST", "/api/shell") for c in self.transport.calls), 1)

    def test_command_refuses_unowned_sessions_bad_argv_and_invalid_timeouts(self):
        self.qualify()
        root = self.create()
        for changes in ({"session": dict(root, owner="other")}, {"driver_id": "other"},
                        {"argv": ["bad\x00argument"]}, {"argv": []}, {"argv": "echo string"},
                        {"timeout_seconds": True}, {"timeout_seconds": 0}):
            self.reject(lambda: self.start(root, **changes) if "session" not in changes else self.start(**changes))
        self.assertFalse(any(c[:2] == ("POST", "/api/shell") for c in self.transport.calls))

    def test_poll_status_only_and_heartbeat_not_progress(self):
        self.qualify()
        command = self.start()
        self.transport.responses[("GET", "/api/shell/sh_owned")] = {
            "location": {"directory": DIRECTORY}, "data": shell_info()}
        result = self.adapter.poll_command(command=command, deadline=100, max_bytes=65536)
        self.assertEqual(result, {"status": "running", "exit": None, "progress": False})
        del self.transport.responses[("GET", "/api/shell/sh_owned")]
        self.assertEqual(self.adapter.poll_command(command=command, deadline=100, max_bytes=65536),
                         {"status": "exited", "exit": 0, "progress": True})

    def test_late_poll_success_and_expired_command_are_not_passes(self):
        self.qualify()
        command = self.start()
        self.clock.now = 18
        self.assertEqual(self.adapter.poll_command(command=command, deadline=100, max_bytes=65536),
                         {"status": "timeout", "exit": None, "progress": False})
        self.clock.now = 10
        self.transport.hook = lambda method, path: setattr(self.clock, "now", 101)
        self.reject(lambda: self.adapter.poll_command(command=command, deadline=100, max_bytes=65536))

    def test_call_byte_deadline_json_and_exception_bounds(self):
        for response in (b"x" * 65537, b'{"duplicate":"SECRET", "duplicate":1}',
                         b'{"x":NaN}', RuntimeError("SECRET_TOKEN")):
            self.transport.calls.clear()
            self.transport.responses = {("GET", "/api/info"): response}
            self.reject(self.qualify)
        self.transport.calls.clear()
        self.reject(lambda: self.qualify(deadline=10))
        self.assertEqual(self.transport.calls, [])

    def test_late_creation_response_is_ambiguous_no_retry(self):
        self.qualify()
        self.transport.hook = lambda method, path: setattr(self.clock, "now", 101)
        self.reject(self.create)
        self.clock.now = 10
        self.reject(self.create)
        self.assertEqual(sum(c[:2] == ("POST", "/api/session") for c in self.transport.calls), 1)

    def test_collect_only_allowlisted_counters_never_output(self):
        self.qualify()
        root = self.create()
        command = self.start(root)
        self.transport.responses[("GET", "/api/shell/sh_owned")] = {
            "location": {"directory": DIRECTORY}, "data": shell_info("exited", 3)}
        result = self.adapter.collect(sessions=[root], commands=[command], deadline=100, max_bytes=65536)
        self.assertEqual(result, {"diagnostics": [{"code": "command_failed", "count": 1},
                                                  {"code": "output_omitted", "count": 1}]})
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertFalse(any("/output" in c[1] or c[0] == "DELETE" for c in self.transport.calls))

    def test_stop_is_scoped_and_interrupt_ack_is_not_proof(self):
        self.qualify()
        root = self.create()
        command = self.start(root)
        self.observer.stop_confirmed = False
        result = self.stop([root], [command])
        self.assertEqual(result, {"confirmed": False, "sessions": [root["id"]],
                                  "commands": [command["id"]], "descendants_stopped": False,
                                  "unrelated_preserved": False})
        interrupts = [c for c in self.transport.calls if c[1].endswith("/interrupt")]
        self.assertEqual(interrupts[-1][2], {"resume": "false"})
        self.assertFalse(any(c[0] == "DELETE" or "service" in c[1] for c in self.transport.calls))

    def test_stop_missing_or_inexact_observer_cannot_confirm(self):
        self.qualify()
        root = self.create()
        self.adapter.observer = None
        self.assertFalse(self.stop([root], [])["confirmed"])
        self.adapter.observer = self.observer
        self.observer.stop = lambda **kwargs: {"confirmed": True, "sessions": ["ses_unrelated"],
             "commands": [], "descendants_stopped": True, "unrelated_preserved": True}
        self.assertFalse(self.stop([root], [])["confirmed"])

    def test_stop_exact_observed_sets_and_no_destructive_output_removal(self):
        self.qualify()
        root = self.create()
        command = self.start(root)
        self.adapter.collect(sessions=[root], commands=[command], deadline=100, max_bytes=65536)
        result = self.stop([root], [command])
        self.assertTrue(result["confirmed"])
        self.assertTrue(result["descendants_stopped"])
        self.assertTrue(result["unrelated_preserved"])
        self.assertFalse(any(c[0] == "DELETE" for c in self.transport.calls))

    def test_forged_poll_collect_stop_records_refused_before_effects(self):
        self.qualify()
        root = self.create()
        command = self.start(root)
        count = len(self.transport.calls)
        self.reject(lambda: self.adapter.poll_command(command=dict(command, owner="other"), deadline=100, max_bytes=65536))
        self.reject(lambda: self.adapter.collect(sessions=[dict(root, id="ses_other")], commands=[], deadline=100, max_bytes=65536))
        self.reject(lambda: self.stop([root], [dict(command, id="sh_unrelated")]))
        self.assertEqual(len(self.transport.calls), count)

    def test_stop_cannot_omit_registered_command(self):
        self.qualify()
        root = self.create()
        self.start(root)
        count = len(self.transport.calls)
        self.reject(lambda: self.stop([root], []))
        self.assertEqual(len(self.transport.calls), count)

    def test_expired_running_command_cannot_suppress_inactivity(self):
        self.qualify()
        command = self.start()
        self.clock.now = 18
        self.transport.responses[("GET", "/api/shell/sh_owned")] = {
            "location": {"directory": DIRECTORY}, "data": shell_info()}
        self.assertEqual(self.adapter.poll_command(command=command, deadline=100, max_bytes=65536),
                         {"status": "timeout", "exit": None, "progress": False})

    def test_ambiguous_creation_cannot_be_confirmed_stopped_as_empty_set(self):
        self.qualify()
        self.transport.responses[("POST", "/api/session")] = TimeoutError("SECRET")
        self.reject(self.create)
        self.assertFalse(self.stop([], [])["confirmed"])

    def test_ambiguous_command_cannot_be_omitted_from_confirmed_stopping(self):
        self.qualify()
        root = self.create()
        self.transport.responses[("POST", "/api/shell")] = TimeoutError("SECRET")
        self.reject(lambda: self.start(root))
        self.assertFalse(self.stop([root], [])["confirmed"])

    def test_failed_child_discovery_cannot_allow_parent_only_confirmation(self):
        self.qualify()
        root = self.create()
        self.transport.pages = [{"data": [session_info("ses_child", root["id"])], "cursor": {"next": None}}]
        self.observer.delegated = []
        self.reject(lambda: self.adapter.discover_children(session=root, directory=DIRECTORY,
                    run_key="project/run", deadline=100, max_bytes=65536))
        self.assertFalse(self.stop([root], [])["confirmed"])

    def test_malformed_unhashable_record_ids_have_fixed_errors(self):
        self.qualify()
        root = self.create()
        command = self.start(root)
        self.reject(lambda: self.stop([dict(root, id=["SECRET"])], [command]))
        self.reject(lambda: self.adapter.poll_command(command=dict(command, id={"SECRET": 1}),
                    deadline=100, max_bytes=65536))

    def test_killed_exit_zero_is_still_failure(self):
        self.qualify()
        root = self.create()
        command = self.start(root)
        self.transport.responses[("GET", "/api/shell/sh_owned")] = {
            "location": {"directory": DIRECTORY}, "data": shell_info("killed", 0)}
        result = self.adapter.collect(sessions=[root], commands=[command], deadline=100, max_bytes=65536)
        self.assertIn({"code": "command_failed", "count": 1}, result["diagnostics"])

    def test_successful_command_duplicate_reuses_record_but_changed_timeout_holds(self):
        self.qualify()
        root = self.create()
        command = self.start(root)
        self.assertEqual(self.start(root), command)
        self.reject(lambda: self.start(root, timeout_seconds=8))
        self.assertEqual(sum(c[:2] == ("POST", "/api/shell") for c in self.transport.calls), 1)

    def test_process_observer_late_returns_are_not_confirmed_or_retried(self):
        self.qualify()
        root = self.create()
        def late(**kwargs):
            self.clock.now = 101
            return [{"pid": 456, "start_id": "987654"}]
        self.observer.processes = late
        self.reject(lambda: self.start(root))
        self.clock.now = 10
        self.assertFalse(self.stop([root], [])["confirmed"])

    def test_stop_interrupt_transport_timeout_preserves_safe_unconfirmed_shape(self):
        self.qualify()
        root = self.create()
        self.transport.responses[("POST", "/api/session/ses_parent/interrupt")] = TimeoutError("SECRET_AUTH")
        result = self.stop([root], [])
        self.assertFalse(result["confirmed"])
        self.assertNotIn("SECRET", json.dumps(result))

    def test_tight_cumulative_byte_bound_refuses_discovery_pages(self):
        self.qualify()
        root = self.create()
        self.transport.pages = [{"data": [session_info("ses_child", root["id"])], "cursor": {"next": None}}]
        self.reject(lambda: self.adapter.discover_children(session=root, directory=DIRECTORY,
                    run_key="project/run", deadline=100, max_bytes=100))

    def test_stopping_unqualified_after_config_drift_still_interrupts_registered_work(self):
        self.qualify()
        root = self.create()
        self.transport.calls.clear()
        self.discovery_result["approved"] = False
        self.reject(self.qualify)
        self.assertTrue(self.stop([root], [])["confirmed"])

    def test_no_effect_for_expired_stop_and_malformed_observer_results(self):
        self.qualify()
        root = self.create()
        count = len(self.transport.calls)
        self.reject(lambda: self.stop([root], [], deadline=10))
        self.assertEqual(len(self.transport.calls), count)
        self.observer.stop = lambda **kwargs: {"confirmed": "SECRET_NOT_BOOL"}
        self.assertFalse(self.stop([root], [])["confirmed"])

    def test_returned_command_changed_by_plugin_is_ambiguous(self):
        self.qualify()
        root = self.create()
        info = shell_info()
        info["command"] = "SECRET_CHANGED_COMMAND"
        self.transport.responses[("POST", "/api/shell")] = {
            "location": {"directory": DIRECTORY}, "data": info}
        self.reject(lambda: self.start(root))
        self.assertFalse(self.stop([root], [])["confirmed"])

    def test_poll_changed_command_identity_is_held(self):
        self.qualify()
        command = self.start()
        info = shell_info("exited", 0)
        info["command"] = "SECRET_CHANGED_COMMAND"
        self.transport.responses[("GET", "/api/shell/sh_owned")] = {
            "location": {"directory": DIRECTORY}, "data": info}
        self.reject(lambda: self.adapter.poll_command(command=command, deadline=100, max_bytes=65536))

    def test_malformed_delegation_observation_has_fixed_error(self):
        self.qualify()
        root = self.create()
        self.transport.pages = [{"data": [session_info("ses_child", root["id"])], "cursor": {"next": None}}]
        self.observer.delegated = [{"SECRET": 1}]
        self.reject(lambda: self.adapter.discover_children(session=root, directory=DIRECTORY,
                    run_key="project/run", deadline=100, max_bytes=65536))

    def test_direct_shell_parent_exit_does_not_prove_observed_descendant_stopped(self):
        self.qualify()
        root = self.create()
        self.observer.identities.append({"pid": 457, "start_id": "987655"})
        command = self.start(root)
        self.assertEqual(self.adapter.poll_command(command=command, deadline=100, max_bytes=65536)["status"], "exited")
        self.observer.stop_confirmed = False
        self.assertFalse(self.stop([root], [command])["descendants_stopped"])
        stopped_commands = self.observer.calls[-1][1]["commands"]
        self.assertEqual(stopped_commands[0]["processes"], self.observer.identities)

    def test_real_tagged_api_fixture_identity_and_request_properties_offline(self):
        path = Path("/tmp/opencode/w2-input-evidence-k93yu_bl/v2.0.22-openapi.json")
        if not path.is_file():
            self.skipTest("Retained tagged input bytes unavailable; no runtime substitute")
        data = path.read_bytes()
        self.assertEqual(digest(data), RELEASE_API_SHA256)
        schema = json.loads(data)
        self.assertEqual(schema["paths"]["/api/config"]["get"]["parameters"][0]["style"], "deepObject")
        self.assertEqual(set(schema["paths"]["/api/shell"]["post"]["requestBody"]["content"]
                             ["application/json"]["schema"]["properties"]), {"command", "cwd", "timeout", "metadata"})
        self.release_patch.stop()
        adapter = self.make_adapter(api_bytes=data)
        self.transport.responses[("GET", "/openapi.json")] = data
        result = self.qualify(adapter, runtime=dict(RUNTIME, api_sha256=RELEASE_API_SHA256), max_bytes=1048576)
        self.assertEqual(result["api_sha256"], RELEASE_API_SHA256)
        self.assertEqual(result["qualification"], "deterministic")

    def test_command_timeout_caps_to_remaining_deadline_including_call_overhead(self):
        self.qualify()
        root = self.create()
        command = self.start(root, deadline=16.875)
        self.assertEqual(self.transport.calls[-1][3]["timeout"], 6875)
        self.clock.now = 17
        self.assertEqual(self.adapter.poll_command(command=command, deadline=100, max_bytes=65536)["status"], "timeout")

    def test_expired_observation_does_not_reclassify_collected_success_as_failure(self):
        self.qualify()
        root = self.create()
        command = self.start(root)
        self.assertEqual(self.adapter.poll_command(command=command, deadline=100, max_bytes=65536)["exit"], 0)
        self.clock.now = 18
        result = self.adapter.collect(sessions=[root], commands=[command], deadline=100, max_bytes=65536)
        self.assertEqual(result, {"diagnostics": [{"code": "output_omitted", "count": 1}]})


if __name__ == "__main__":
    unittest.main()
