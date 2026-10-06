"""Builder-authored W2 lifecycle contracts; fake observations are not qualification."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

from w2_fixture import FakeAdapter, FakeClock, SimulatedCrash, W2Fixture, canonical, digest
from routine.contracts import RoutineError
from routine.launcher import Coordinator, Launcher


class W2InterfaceTests(unittest.TestCase):
    def test_local_lifecycle_interface_exists(self):
        module = importlib.import_module("routine.local_lifecycle")
        clock = FakeClock()
        lifecycle = module.LocalLifecycle(FakeAdapter(clock), clock=clock.time,
                                          monotonic=clock.monotonic,
                                          sleep=clock.sleep, checkpoint=None)
        self.assertTrue(callable(lifecycle.prepare))
        self.assertTrue(callable(lifecycle.fixture_check))

    def test_launcher_accepts_injected_local_adapter(self):
        with W2Fixture() as fixture:
            Launcher(fixture.store, local_adapter=FakeAdapter())

    def test_coordinator_and_trusted_stop_interfaces_exist(self):
        for name in ("local_prepare", "local_fixture_check", "local_stop"):
            self.assertTrue(callable(getattr(Coordinator, name, None)), name)
        self.assertTrue(callable(getattr(Launcher, "local_stop", None)))


def contains_identity(value, identity):
    """Look for registered identity without assuming undocumented ledger wrappers."""
    if isinstance(value, dict):
        return value.get("id") == identity or any(contains_identity(item, identity) for item in value.values())
    if isinstance(value, list):
        return any(contains_identity(item, identity) for item in value)
    return value == identity


class W2FixtureTests(unittest.TestCase):
    def test_shared_fixture_is_not_a_testcase_or_historical_test_import(self):
        self.assertFalse(issubclass(W2Fixture, unittest.TestCase))
        with W2Fixture() as fixture:
            self.assertEqual(fixture.store.read()["runs"], {})
            self.assertTrue(fixture.base.is_relative_to(Path("/tmp/opencode")))
            for role in ("orchestrator", "builder", "tester", "reviewer"):
                self.assertTrue((fixture.bundle / f"agents/{role}.md").is_file())

    def test_prepared_qualification_assets_are_independent_clones_not_runtime_proof(self):
        with W2Fixture() as fixture:
            original = (fixture.root / "routing-canary.txt").read_bytes()
            clones = fixture.prepare_routing_assets()
            self.assertEqual(len(clones), 2)
            self.assertNotEqual(clones[0], clones[1])
            self.assertNotEqual((clones[0] / ".git").stat().st_ino, (clones[1] / ".git").stat().st_ino)
            for clone in clones:
                self.assertTrue((clone / ".git").is_dir())
                self.assertFalse((clone / ".git/objects/info/alternates").exists())
                self.assertFalse((clone / ".git/commondir").exists())
                self.assertEqual(fixture.git("rev-parse", "HEAD", cwd=clone).strip(), fixture.commit)
            self.assertNotEqual((clones[0] / "routing-canary.txt").read_bytes(),
                                (clones[1] / "routing-canary.txt").read_bytes())
            self.assertEqual((fixture.root / "routing-canary.txt").read_bytes(), original)
            self.assertEqual(fixture.store.read()["runs"], {})


class W2LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.fixture = W2Fixture()
        self.addCleanup(self.fixture.close)
        self.clock = FakeClock()
        self.adapter = FakeAdapter(self.clock)
        # Interface import failure is intentional RED, never a skip/fake product.
        self.lifecycle_class = importlib.import_module("routine.local_lifecycle").LocalLifecycle
        self.lifecycle = self.new_lifecycle()

    def new_lifecycle(self, adapter=None, checkpoint=None):
        return self.lifecycle_class(self.adapter if adapter is None else adapter,
                                    clock=self.clock.time, monotonic=self.clock.monotonic,
                                    sleep=self.clock.sleep, checkpoint=checkpoint)

    def prepare(self, coordinator):
        return self.lifecycle.prepare(coordinator, "run-1")

    def check(self, coordinator):
        return self.lifecycle.fixture_check(coordinator, "run-1")

    def execute(self, coordinator):
        self.prepare(coordinator)
        return self.check(coordinator)

    def rejected_or_held(self, operation):
        """Documented safe refusal may be a RoutineError or a held/failed run."""
        try:
            result = operation()
        except RoutineError as error:
            return error
        self.assertIn(result["run"]["state"], ("local-held", "local-failed"))
        return result

    def assert_no_integration(self):
        feature = self.fixture.feature()
        self.assertEqual(feature["verified_head"], self.fixture.manifest["baseline"])
        self.assertNotEqual(feature["slices"]["01"]["state"], "integrated")
        self.assertNotEqual(self.fixture.run().get("result", {}).get("outcome"), "ready-for-integration")

    def assert_held_repeat_has_no_effects_or_budget_reset(self, coordinator):
        before = deepcopy(self.fixture.run())
        self.assertEqual(before["state"], "local-held")
        calls = deepcopy(self.adapter.calls)
        self.clock.advance(7)
        for operation in (self.prepare, self.check):
            result = operation(coordinator)
            self.assertTrue(result["existing"])
            self.assertEqual(result["run"]["state"], "local-held")
        after = self.fixture.run()
        self.assertEqual(self.adapter.calls, calls)
        for key in ("runtime_started_at", "runtime_deadline"):
            self.assertEqual(after["local"][key], before["local"][key])
        self.assertEqual(after["budgets"], before["budgets"])
        self.assert_no_integration()

    def test_prepare_is_idempotent_and_retains_exact_independent_baseline(self):
        with self.fixture.claimed() as (coordinator, claim):
            self.assertNotIn("local", claim)
            result = self.prepare(coordinator)
            self.assertFalse(result["existing"])
            run = result["run"]
            self.assertEqual(run["state"], "local-prepared")
            local = run["local"]
            self.assertEqual(local["version"], 1)
            self.assertEqual(local["runtime_started_at"], 1700000000.0)
            self.assertEqual(local["runtime_deadline"], 1700000120.0)
            prepared = local["prepared"]
            self.assertEqual(prepared["commit"], self.fixture.commit)
            self.assertEqual(prepared["branch"], "routine/feature/01/run-1")
            checkout = Path(prepared["checkout"])
            self.assertNotEqual(checkout, self.fixture.root)
            self.assertTrue(checkout.is_relative_to(self.fixture.store.root))
            self.assertTrue((checkout / ".git").is_dir())
            self.assertNotEqual((checkout / ".git").stat().st_ino, (self.fixture.root / ".git").stat().st_ino)
            self.assertFalse((checkout / ".git/objects/info/alternates").exists())
            self.assertEqual(self.fixture.git("rev-parse", "HEAD", cwd=checkout).strip(), self.fixture.commit)
            self.assertEqual(self.fixture.git("symbolic-ref", "--short", "HEAD", cwd=checkout).strip(), prepared["branch"])
            before = deepcopy(run)
            self.clock.advance(2)
            repeated = self.prepare(coordinator)
            self.assertTrue(repeated["existing"])
            self.assertEqual(repeated["run"], before)
            self.assertEqual(self.adapter.calls, [])

    def test_handoff_contains_exact_planning_profile_approval_and_full_frozen_bundle(self):
        with self.fixture.claimed() as (coordinator, _):
            run = self.prepare(coordinator)["run"]
            handoff = run["local"]["prepared"]["handoff"]
            root = Path(handoff["path"])
            inventory = handoff["inventory"]
            self.assertEqual(inventory, sorted(inventory, key=lambda item: item["path"]))
            self.assertEqual(digest(canonical(inventory)), handoff["sha256"])
            actual = {path.relative_to(root).as_posix(): path.read_bytes()
                      for path in root.rglob("*") if path.is_file()}
            self.assertEqual({name: digest(data) for name, data in actual.items()},
                             {item["path"]: item["sha256"] for item in inventory})
            self.assertFalse(any(path.is_symlink() for path in root.rglob("*")))
            required = [self.fixture.root / self.fixture.manifest["spec"]["path"],
                        self.fixture.root / ".opencode/routine/project.json",
                        self.fixture.root / ".opencode/routine/features/feature/approval.json"]
            required.extend(self.fixture.root / ticket["path"] for ticket in self.fixture.manifest["tickets"])
            required.extend(path for path in self.fixture.bundle.rglob("*") if path.is_file())
            for source in required:
                self.assertIn(source.read_bytes(), actual.values(), source.name)

    def test_fixture_success_collects_then_stops_and_is_never_integrated(self):
        with self.fixture.claimed() as (coordinator, _):
            result = self.execute(coordinator)
            self.assertFalse(result["existing"])
            run = result["run"]
            self.assertEqual(run["state"], "local-fixture-passed")
            evidence = run["result"]
            self.assertEqual(evidence["execution"], "trusted-local")
            self.assertEqual(evidence["outcome"], "fixture-passed")
            self.assertEqual(evidence["qualification"], "deterministic")
            self.assertRegex(evidence["evidence_sha256"], r"^[0-9a-f]{64}$")
            names = self.adapter.names()
            self.assertLess(names.index("qualify"), names.index("create_session"))
            self.assertLess(names.index("create_session"), names.index("start_command"))
            self.assertLess(names.index("collect"), names.index("stop"))
            self.assert_no_integration()
            self.assertEqual(self.fixture.launcher.status("project", "feature")["slices"]["02"]["waiting_for"], ["01"])
            self.assertTrue(Path(run["local"]["prepared"]["checkout"]).is_dir())
            evidence_files = list((Path(run["local"]["prepared"]["artifact"]) / "evidence").glob("*.json"))
            self.assertTrue(any(digest(path.read_bytes().rstrip(b"\n")) == evidence["evidence_sha256"]
                                for path in evidence_files))

    def test_completed_duplicate_requests_preserve_results_timers_repairs_and_effect_counts(self):
        with self.fixture.claimed() as (coordinator, _):
            before = deepcopy(self.execute(coordinator)["run"])
            self.assertEqual(before["state"], "local-fixture-passed")
            calls = deepcopy(self.adapter.calls)
            self.clock.advance(200)
            for operation in (self.prepare, self.check):
                result = operation(coordinator)
                self.assertTrue(result["existing"])
                self.assertEqual(result["run"], before)
            self.assertEqual(self.adapter.calls, calls)
            self.assert_no_integration()

    def test_approved_setup_then_named_checks_are_exact_argv_and_location(self):
        self.fixture.profile["commands"]["setup"] = [
            {"argv": ["python3", "-B", "fixture_commands.py", "setup", "literal;not-shell"], "timeout_seconds": 20}]
        self.fixture.profile["commands"]["checks"]["lint"] = {
            "argv": ["python3", "-B", "fixture_commands.py", "lint", "a b", "$(not-expanded)"], "timeout_seconds": 10}
        self.fixture.save_profile()
        with self.fixture.claimed() as (coordinator, _):
            run = self.execute(coordinator)["run"]
            calls = self.adapter.arguments("start_command")
            expected = self.fixture.profile["commands"]["setup"] + list(self.fixture.profile["commands"]["checks"].values())
            self.assertEqual(calls[0]["argv"], expected[0]["argv"])
            self.assertCountEqual([call["argv"] for call in calls[1:]], [command["argv"] for command in expected[1:]])
            checkout = str(Path(run["local"]["prepared"]["checkout"]).resolve())
            for call in calls:
                self.assertEqual(str(call["directory"]), checkout)
                self.assertEqual(call["run_key"], "project/run-1")
                self.assertEqual(call["session"]["directory"], checkout)
                approved = next(command for command in expected if command["argv"] == call["argv"])
                self.assertLessEqual(call["timeout_seconds"], approved["timeout_seconds"])

    def test_setup_failure_stops_without_starting_checks_or_consuming_repairs(self):
        self.fixture.profile["commands"]["setup"] = [
            {"argv": ["python3", "-B", "fixture_commands.py", "setup"], "timeout_seconds": 20}]
        self.fixture.save_profile()
        self.adapter.polls.append({"status": "exited", "exit": 17, "progress": False})
        self.adapter.responses["collect"] = {"diagnostics": [{"code": "command_failed", "count": 1}]}
        with self.fixture.claimed() as (coordinator, claim):
            run = self.execute(coordinator)["run"]
            self.assertEqual(run["state"], "local-failed")
            self.assertEqual(run["result"]["outcome"], "failed")
            self.assertEqual(len(self.adapter.arguments("start_command")), 1)
            self.assertEqual(run["budgets"], claim["budgets"])
            self.assertIn({"code": "command_failed", "count": 1}, run["local"]["diagnostics"])
            self.assertEqual(run["local"]["checks"][0]["exit"], 17)
            self.assertEqual(run["local"]["checks"][0]["outcome"], "failed")
            self.assertIn("stop", self.adapter.names())
            self.assertTrue(Path(run["local"]["prepared"]["checkout"]).is_dir())
            self.assert_no_integration()

    def test_intent_and_runtime_budget_are_durable_before_clone_effect(self):
        helper = importlib.import_module("routine.local_run")
        real_prepare = helper.prepare_clone
        observed = []

        def inspect(feature, run, destination, *, timeout, max_bytes, checkpoint):
            durable = self.fixture.run()["local"]
            self.assertEqual(durable["runtime_started_at"], self.clock.time())
            self.assertEqual(durable["runtime_deadline"], self.clock.time() + 120)
            self.assertTrue(durable["driver"]["id"])
            self.assertEqual(durable["checkpoints"][-1]["phase"], "intent")
            self.assertFalse(Path(destination).exists())
            observed.append(True)
            return real_prepare(feature, run, destination, timeout=timeout, max_bytes=max_bytes, checkpoint=checkpoint)

        with self.fixture.claimed() as (coordinator, _), patch.object(helper, "prepare_clone", side_effect=inspect):
            self.prepare(coordinator)
        self.assertEqual(observed, [True])

    def test_session_and_command_creation_intents_precede_effects_and_identities_precede_use(self):
        observed = []

        def intent(arguments):
            local = self.fixture.run()["local"]
            latest = local["checkpoints"][-1]
            self.assertEqual(latest["phase"], "intent")
            self.assertEqual(local["driver"]["id"], arguments["driver_id"])
            self.assertTrue(local["prepared"])
            observed.append(latest["sequence"])

        def command_intent(arguments):
            intent(arguments)
            local = self.fixture.run()["local"]
            self.assertTrue(contains_identity(local["sessions"], arguments["session"]["id"]))

        def poll_registered(arguments):
            self.assertTrue(contains_identity(self.fixture.run()["local"]["commands"], arguments["command"]["id"]))

        self.adapter.hooks.update(create_session=intent, start_command=command_intent, poll_command=poll_registered)
        with self.fixture.claimed() as (coordinator, _):
            run = self.execute(coordinator)["run"]
            checkpoints = run["local"]["checkpoints"]
            self.assertEqual([item["sequence"] for item in checkpoints], sorted(set(item["sequence"] for item in checkpoints)))
            self.assertTrue(all(set(item) == {"sequence", "effect", "phase", "at", "identity"} for item in checkpoints))
            self.assertEqual(len(observed), 2)

    def test_clone_interruption_preserves_partial_artifact_and_is_not_retried(self):
        helper = importlib.import_module("routine.local_run")
        partials = []

        def fail(feature, run, destination, *, timeout, max_bytes, checkpoint):
            destination = Path(destination)
            destination.mkdir()
            (destination / "partial-canary").write_bytes(b"retain interrupted preparation\n")
            partials.append(destination)
            raise OSError("W2_SECRET_CANARY partial preparation")

        with self.fixture.claimed() as (coordinator, _), patch.object(helper, "prepare_clone", side_effect=fail) as preparation:
            self.rejected_or_held(lambda: self.prepare(coordinator))
            self.assertEqual(self.fixture.run()["state"], "local-held")
            self.assert_held_repeat_has_no_effects_or_budget_reset(coordinator)
            self.assertEqual(preparation.call_count, 1)
            self.assertEqual((partials[0] / "partial-canary").read_bytes(), b"retain interrupted preparation\n")
            self.assertNotIn("W2_SECRET_CANARY", json.dumps(self.fixture.run()))

    def test_ambiguous_session_creation_holds_without_second_create(self):
        self.adapter.responses["create_session"] = OSError("W2_SECRET_CANARY reply lost after creation")
        with self.fixture.claimed() as (coordinator, _):
            self.rejected_or_held(lambda: self.execute(coordinator))
            self.assertEqual(len(self.adapter.arguments("create_session")), 1)
            self.assertEqual(self.adapter.arguments("start_command"), [])
            self.assert_held_repeat_has_no_effects_or_budget_reset(coordinator)
            self.assertNotIn("W2_SECRET_CANARY", json.dumps(self.fixture.run()))

    def test_ambiguous_command_creation_holds_without_second_start(self):
        self.adapter.responses["start_command"] = OSError("W2_SECRET_CANARY reply lost after command effect")
        with self.fixture.claimed() as (coordinator, _):
            self.rejected_or_held(lambda: self.execute(coordinator))
            self.assertEqual(len(self.adapter.arguments("start_command")), 1)
            self.assert_held_repeat_has_no_effects_or_budget_reset(coordinator)

    def test_crashes_at_adapter_effect_boundaries_never_resume_or_duplicate(self):
        # Each subcase has its own disposable ledger and IDs; no state reset/recovery.
        for method in ("qualify", "create_session", "start_command", "collect", "stop"):
            with self.subTest(method=method), W2Fixture() as fixture:
                previous_fixture, previous_adapter = self.fixture, self.adapter
                self.fixture = fixture
                self.adapter = FakeAdapter(self.clock)
                self.lifecycle = self.new_lifecycle()
                self.adapter.responses[method] = SimulatedCrash("driver interrupted")
                try:
                    with fixture.claimed() as (coordinator, _):
                        with self.assertRaises(SimulatedCrash):
                            self.execute(coordinator)
                        calls = deepcopy(self.adapter.calls)
                        local = deepcopy(fixture.run()["local"])
                        self.lifecycle = self.new_lifecycle()
                        repeated = self.check(coordinator)
                        self.assertEqual(repeated["run"]["state"], "local-held")
                        self.assertEqual(self.adapter.calls, calls)
                        for key in ("runtime_started_at", "runtime_deadline"):
                            self.assertEqual(fixture.run()["local"][key], local[key])
                        self.assertTrue(Path(local["prepared"]["checkout"]).is_dir())
                        self.assert_held_repeat_has_no_effects_or_budget_reset(coordinator)
                finally:
                    self.fixture, self.adapter = previous_fixture, previous_adapter
                    self.lifecycle = self.new_lifecycle()

    def test_configuration_identity_or_observation_gaps_hold_before_session_creation(self):
        alterations = {"api_sha256": "f" * 64, "configuration_sha256": "f" * 64,
                       "bundle_sha256": "f" * 64, "directory": "/unapproved/other-clone",
                       "permissions_verified": False, "stopping_verified": False, "delegation_verified": False}
        for field, value in alterations.items():
            with self.subTest(field=field), W2Fixture() as fixture:
                adapter = FakeAdapter(self.clock)
                def altered(arguments, field=field, value=value):
                    normal = FakeAdapter(self.clock).qualify(**arguments)
                    normal[field] = value
                    return normal
                adapter.responses["qualify"] = altered
                lifecycle = self.new_lifecycle(adapter)
                with fixture.claimed() as (coordinator, _):
                    lifecycle.prepare(coordinator, "run-1")
                    self.rejected_or_held(lambda: lifecycle.fixture_check(coordinator, "run-1"))
                    self.assertEqual(fixture.run()["state"], "local-held")
                    self.assertNotIn("create_session", adapter.names())
                    self.assertNotIn("start_command", adapter.names())

    def test_missing_adapter_fails_closed_without_runtime_effects(self):
        # Explicit None uses only the approved assembled adapter, which cannot infer
        # a service/connection from this offline fixture's identifier.
        lifecycle = self.lifecycle_class(None, clock=self.clock.time,
                                         monotonic=self.clock.monotonic, sleep=self.clock.sleep)
        with self.fixture.claimed() as (coordinator, _):
            lifecycle.prepare(coordinator, "run-1")
            self.rejected_or_held(lambda: lifecycle.fixture_check(coordinator, "run-1"))
            self.assertNotEqual(self.fixture.run()["state"], "local-fixture-passed")
            self.assertEqual(self.adapter.calls, [])

    def test_quiet_live_command_outlasts_inactivity_but_not_its_own_deadline(self):
        self.adapter.polls.extend([{"status": "running", "exit": None, "progress": False}] * 3 +
                                 [{"status": "exited", "exit": 0, "progress": False}])
        self.adapter.delays["poll_command"] = 3
        with self.fixture.claimed() as (coordinator, _):
            run = self.execute(coordinator)["run"]
            self.assertEqual(run["state"], "local-fixture-passed")
            self.assertGreaterEqual(len(self.adapter.arguments("poll_command")), 4)
            self.assertGreater(self.clock.time() - run["local"]["runtime_started_at"], 5)

    def test_live_heartbeat_never_resets_progress_or_extends_command_timeout(self):
        self.adapter.polls.append({"status": "running", "exit": None, "progress": False})
        self.adapter.delays["poll_command"] = 4
        with self.fixture.claimed() as (coordinator, _):
            self.prepare(coordinator)
            initial_progress = self.fixture.run()["local"]["last_progress_at"]
            run = self.check(coordinator)["run"]
            self.assertEqual(run["state"], "local-failed")
            self.assertEqual(run["local"]["last_progress_at"], initial_progress)
            self.assertLess(len(self.adapter.arguments("poll_command")), 20)
            self.assertIn("stop", self.adapter.names())
            self.assert_no_integration()

    def test_late_command_success_is_timeout_not_pass(self):
        self.adapter.delays["poll_command"] = 31
        with self.fixture.claimed() as (coordinator, _):
            run = self.execute(coordinator)["run"]
            self.assertNotEqual(run["state"], "local-fixture-passed")
            self.assertNotEqual(run.get("result", {}).get("outcome"), "fixture-passed")
            self.assertIn("collect", self.adapter.names())
            self.assertIn("stop", self.adapter.names())
            self.assert_no_integration()

    def test_preparation_time_counts_and_repeat_never_restarts_slice_budget(self):
        with self.fixture.claimed() as (coordinator, _):
            before = self.prepare(coordinator)["run"]["local"]
            self.clock.advance(121)
            self.rejected_or_held(lambda: self.check(coordinator))
            after = self.fixture.run()["local"]
            self.assertEqual(after["runtime_started_at"], before["runtime_started_at"])
            self.assertEqual(after["runtime_deadline"], before["runtime_deadline"])
            self.assertNotIn("start_command", self.adapter.names())

    def test_every_adapter_call_has_absolute_deadline_and_approved_byte_bound(self):
        with self.fixture.claimed() as (coordinator, _):
            run = self.execute(coordinator)["run"]
            remaining = run["local"]["runtime_deadline"] - 1700000000.0
            for (name, arguments), ticks in zip(self.adapter.calls, self.adapter.call_times):
                with self.subTest(method=name):
                    self.assertGreater(arguments["deadline"], ticks)
                    self.assertLessEqual(arguments["deadline"], 100.0 + remaining)
                    self.assertLessEqual(arguments["deadline"] - ticks, 60)
                    if "max_bytes" in arguments:
                        self.assertGreater(arguments["max_bytes"], 0)
                        self.assertLessEqual(arguments["max_bytes"], 1048576)

    def test_late_qualification_and_session_returns_cannot_advance_to_commands(self):
        for method in ("qualify", "create_session"):
            with self.subTest(method=method), W2Fixture() as fixture:
                adapter = FakeAdapter(self.clock)
                adapter.delays[method] = 61
                lifecycle = self.new_lifecycle(adapter)
                with fixture.claimed() as (coordinator, _):
                    lifecycle.prepare(coordinator, "run-1")
                    self.rejected_or_held(lambda: lifecycle.fixture_check(coordinator, "run-1"))
                    self.assertNotIn("start_command", adapter.names())
                    self.assertNotEqual(fixture.run()["state"], "local-fixture-passed")

    def test_diagnostics_are_durable_before_destructive_stop(self):
        diagnostics = [{"code": "output_omitted", "count": 3}]
        self.adapter.responses["collect"] = {"diagnostics": diagnostics}
        def inspect(arguments):
            run = self.fixture.run()
            self.assertEqual(run["local"]["diagnostics"], diagnostics)
            self.assertTrue(contains_identity(run["local"]["sessions"], arguments["sessions"][0]["id"]))
            self.assertTrue(contains_identity(run["local"]["commands"], arguments["commands"][0]["id"]))
        self.adapter.hooks["stop"] = inspect
        with self.fixture.claimed() as (coordinator, _):
            self.assertEqual(self.execute(coordinator)["run"]["state"], "local-fixture-passed")

    def test_uncertain_stop_acknowledgement_missing_sets_or_descendants_is_held(self):
        mutations = [lambda result: result.update(confirmed=False),
                     lambda result: result.update(descendants_stopped=False),
                     lambda result: result.update(unrelated_preserved=False),
                     lambda result: result.update(sessions=[]),
                     lambda result: result.update(commands=[]),
                     lambda result: result["sessions"].append("user-session")]
        for mutation in mutations:
            with self.subTest(mutation=mutation), W2Fixture() as fixture:
                adapter = FakeAdapter(self.clock)
                def uncertain(arguments, mutation=mutation):
                    result = FakeAdapter(self.clock).stop(**arguments)
                    mutation(result)
                    return result
                adapter.responses["stop"] = uncertain
                lifecycle = self.new_lifecycle(adapter)
                with fixture.claimed() as (coordinator, _):
                    lifecycle.prepare(coordinator, "run-1")
                    self.rejected_or_held(lambda: lifecycle.fixture_check(coordinator, "run-1"))
                    self.assertEqual(fixture.run()["state"], "local-held")
                    before = deepcopy(adapter.calls)
                    self.assertEqual(lifecycle.fixture_check(coordinator, "run-1")["run"]["state"], "local-held")
                    self.assertEqual(adapter.calls, before)

    def test_collection_failure_retains_artifacts_and_never_reports_a_pass(self):
        self.adapter.responses["collect"] = OSError("W2_SECRET_CANARY lost diagnostics")
        with self.fixture.claimed() as (coordinator, _):
            self.rejected_or_held(lambda: self.execute(coordinator))
            self.assertEqual(self.fixture.run()["state"], "local-held")
            self.assertTrue(Path(self.fixture.run()["local"]["prepared"]["checkout"]).is_dir())
            self.assertNotIn("W2_SECRET_CANARY", json.dumps(self.fixture.run()))
            self.assert_held_repeat_has_no_effects_or_budget_reset(coordinator)

    def test_raw_collection_output_and_secret_exception_strings_never_enter_evidence(self):
        self.adapter.responses["collect"] = {"diagnostics": [{"code": "output_omitted", "count": 1}],
                                             "output": "W2_SECRET_CANARY", "Authorization": "Bearer W2_SECRET_CANARY"}
        with self.fixture.claimed() as (coordinator, _):
            self.rejected_or_held(lambda: self.execute(coordinator))
            self.assertNotIn("W2_SECRET_CANARY", json.dumps(self.fixture.store.read()))
            self.assert_no_integration()

    def test_invalid_session_ownership_or_directory_is_not_used_for_commands_or_unowned_stop(self):
        for changed in ({"owner": "project/other-run"}, {"directory": "/unapproved/other-clone"},
                        {"parent_id": "unrelated-parent"}):
            with self.subTest(changed=changed), W2Fixture() as fixture:
                adapter = FakeAdapter(self.clock)
                adapter.responses["create_session"] = lambda args, changed=changed: {
                    "id": "ses_foreign", "directory": str(args["directory"]),
                    "parent_id": None, "owner": args["run_key"], **changed}
                lifecycle = self.new_lifecycle(adapter)
                with fixture.claimed() as (coordinator, _):
                    lifecycle.prepare(coordinator, "run-1")
                    self.rejected_or_held(lambda: lifecycle.fixture_check(coordinator, "run-1"))
                    self.assertNotIn("start_command", adapter.names())
                    for call in adapter.arguments("stop"):
                        self.assertFalse(contains_identity(call["sessions"], "ses_foreign"))

    def test_owned_children_are_registered_and_stopped_along_with_command_descendants(self):
        def children(arguments):
            return [{"id": "ses_child_1", "directory": str(arguments["directory"]),
                     "parent_id": arguments["session"]["id"], "owner": arguments["run_key"]},
                    {"id": "ses_grandchild_1", "directory": str(arguments["directory"]),
                     "parent_id": "ses_child_1", "owner": arguments["run_key"]}]
        self.adapter.responses["discover_children"] = children
        self.adapter.responses["start_command"] = lambda args: {
            "id": "sh_command_with_descendant", "directory": str(args["directory"]),
            "session_id": args["session"]["id"], "owner": args["run_key"],
            "processes": [{"pid": 900001, "start_id": "exited-parent"},
                          {"pid": 900002, "start_id": "still-owned-descendant"}]}
        unrelated = deepcopy(self.adapter.unrelated)
        with self.fixture.claimed() as (coordinator, _):
            run = self.execute(coordinator)["run"]
            self.assertEqual(run["state"], "local-fixture-passed")
            stop = self.adapter.arguments("stop")[-1]
            self.assertEqual({session["id"] for session in stop["sessions"]}, {"ses_fixture_1", "ses_child_1", "ses_grandchild_1"})
            self.assertEqual(stop["commands"][0]["processes"], self.adapter.commands[0]["processes"])
            self.assertEqual(self.adapter.unrelated, unrelated)

    def test_invalid_child_parent_chain_holds_without_stopping_foreign_children(self):
        self.adapter.responses["discover_children"] = lambda args: [{
            "id": "ses_foreign_child", "directory": str(args["directory"]),
            "parent_id": "not-owned-parent", "owner": args["run_key"]}]
        with self.fixture.claimed() as (coordinator, _):
            self.rejected_or_held(lambda: self.execute(coordinator))
            self.assertEqual(self.fixture.run()["state"], "local-held")
            for call in self.adapter.arguments("stop"):
                self.assertFalse(contains_identity(call["sessions"], "ses_foreign_child"))

    def test_driver_fencing_prevents_stale_result_publication(self):
        def fence(arguments):
            self.fixture.mutate_ledger(lambda ledger: ledger["runs"]["project/run-1"]["local"]["driver"].update(id="replacement-driver"))
        self.adapter.hooks["poll_command"] = fence
        with self.fixture.claimed() as (coordinator, _):
            try:
                self.execute(coordinator)
            except RoutineError:
                pass
            run = self.fixture.run()
            self.assertEqual(run["local"]["driver"]["id"], "replacement-driver")
            self.assertNotEqual(run["state"], "local-fixture-passed")
            self.assertNotEqual(run.get("result", {}).get("outcome"), "fixture-passed")
            self.assert_no_integration()

    def test_closed_coordinator_cannot_prepare_or_execute(self):
        with self.fixture.claimed() as (coordinator, _):
            pass
        before = self.fixture.store.read()
        for operation in (self.prepare, self.check):
            with self.assertRaises(RoutineError):
                operation(coordinator)
        self.assertEqual(self.fixture.store.read(), before)
        self.assertEqual(self.adapter.calls, [])

    def test_changed_inputs_hold_before_runtime_effects(self):
        with self.fixture.claimed() as (coordinator, _):
            path = self.fixture.root / self.fixture.manifest["spec"]["path"]
            path.write_bytes(path.read_bytes() + b"\nChanged after claim\n")
            self.rejected_or_held(lambda: self.prepare(coordinator))
            self.assertEqual(self.adapter.calls, [])
            self.assertNotEqual(self.fixture.run()["state"], "local-fixture-passed")

    def test_local_stop_persists_request_without_waiting_for_active_lifecycle_lock(self):
        # Trusted-stop has no clock argument. Give the injected driver a future
        # epoch so the real administration clock cannot misclassify it as expired.
        # Only timing-free lock/request assertions use the trusted-stop entry point.
        self.clock.advance(400000000)
        entered, release = threading.Event(), threading.Event()
        self.adapter.hooks["poll_command"] = lambda arguments: (entered.set(), release.wait(5))
        with self.fixture.claimed() as (coordinator, _):
            self.prepare(coordinator)
            with ThreadPoolExecutor(max_workers=2) as pool:
                worker = pool.submit(self.check, coordinator)
                try:
                    self.assertTrue(entered.wait(3), "Driver did not reach deterministic blocking point")
                    stop = pool.submit(self.fixture.launcher.local_stop, "project", "feature", "run-1")
                    stop.result(timeout=1)
                    request = deepcopy(self.fixture.run()["local"]["stop_request"])
                    self.assertEqual(set(request), {"id", "requested_at"})
                    self.assertTrue(request["id"])
                    self.assertFalse(worker.done(), "Stop request must not need the lifecycle driver to return")
                    self.assertNotEqual(self.fixture.run()["state"], "local-held",
                                        "A live responsive driver owns stopping; request alone is not missing ownership")
                    self.fixture.launcher.local_stop("project", "feature", "run-1")
                    self.assertEqual(self.fixture.run()["local"]["stop_request"], request)
                finally:
                    release.set()
                result = worker.result(timeout=5)
                self.assertNotEqual(result["run"]["state"], "local-fixture-passed")
            self.assertIn("collect", self.adapter.names())
            self.assertIn("stop", self.adapter.names())
            self.assertLess(self.adapter.names().index("collect"), self.adapter.names().index("stop"))
            self.assert_no_integration()

    def test_stop_without_driver_is_held_and_does_not_take_over_or_execute(self):
        with self.fixture.claimed() as (coordinator, _):
            self.prepare(coordinator)
            before = deepcopy(self.fixture.run()["local"])
        self.fixture.launcher.local_stop("project", "feature", "run-1")
        run = self.fixture.run()
        self.assertEqual(run["state"], "local-held")
        self.assertTrue(run["local"]["stop_request"]["id"])
        self.assertEqual(run["local"]["runtime_started_at"], before["runtime_started_at"])
        self.assertEqual(self.adapter.calls, [])

    def test_stop_is_stopping_only_and_does_not_claim_runs_or_open_a_new_lease(self):
        self.fixture.authorize()
        before = self.fixture.store.read()
        with self.assertRaises(RoutineError):
            self.fixture.launcher.local_stop("project", "feature", "missing-run")
        self.assertEqual(self.fixture.store.read(), before)
        with self.fixture.claimed() as (coordinator, _):
            token = self.fixture.feature()["coordinator"]["token"]
            self.fixture.launcher.local_stop("project", "feature", "run-1")
            self.assertEqual(self.fixture.feature()["coordinator"]["token"], token)
            self.assertEqual(len(self.fixture.store.read()["runs"]), 1)
            self.assertEqual(self.adapter.calls, [])

    def test_unrelated_state_and_original_checkout_are_retained_on_success(self):
        self.fixture.authorize()
        retained = {"qa": {"human": {"owner": "user", "state": "running"}},
                    "inspections": {"old": {"retained": True}},
                    "environments": {"old-sandbox": {"state": "retained"}},
                    "unrelated": {"nested": [1, {"keep": "exactly"}]}}
        self.fixture.mutate_ledger(lambda ledger: ledger.update(deepcopy(retained)))
        originals = {path.relative_to(self.fixture.root).as_posix(): path.read_bytes()
                     for path in self.fixture.root.rglob("*") if path.is_file()}
        with self.fixture.claimed() as (coordinator, _):
            self.assertEqual(self.execute(coordinator)["run"]["state"], "local-fixture-passed")
        ledger = self.fixture.store.read()
        for key, value in retained.items():
            self.assertEqual(ledger[key], value)
        self.assertEqual(originals, {path.relative_to(self.fixture.root).as_posix(): path.read_bytes()
                                    for path in self.fixture.root.rglob("*") if path.is_file()})

    def test_concurrent_duplicate_request_cannot_create_a_second_session(self):
        entered, release = threading.Event(), threading.Event()
        self.adapter.hooks["create_session"] = lambda arguments: (entered.set(), release.wait(5))
        with self.fixture.claimed() as (coordinator, _):
            self.prepare(coordinator)
            with ThreadPoolExecutor(max_workers=2) as pool:
                worker = pool.submit(self.check, coordinator)
                try:
                    self.assertTrue(entered.wait(3))
                    duplicate = pool.submit(self.check, coordinator)
                    try:
                        repeated = duplicate.result(timeout=1)
                        self.assertNotEqual(repeated["run"]["state"], "local-fixture-passed")
                    except RoutineError:
                        pass
                    self.assertEqual(len(self.adapter.arguments("create_session")), 1)
                finally:
                    release.set()
                worker.result(timeout=5)
            self.assertEqual(len(self.adapter.arguments("create_session")), 1)

    def test_invalid_command_identity_never_polls_or_stops_unowned_processes(self):
        changes = ({"owner": "project/other-run"}, {"directory": "/unapproved/other-clone"},
                   {"session_id": "ses_unrelated"}, {"processes": []},
                   {"processes": [{"pid": True, "start_id": "fixture"}]},
                   {"processes": [{"pid": 900001, "start_id": ""}]})
        for changed in changes:
            with self.subTest(changed=changed), W2Fixture() as fixture:
                adapter = FakeAdapter(self.clock)
                adapter.responses["start_command"] = lambda args, changed=changed: {
                    "id": "sh_foreign", "directory": str(args["directory"]), "owner": args["run_key"],
                    "session_id": args["session"]["id"], "processes": [{"pid": 900001, "start_id": "fixture"}],
                    **changed}
                lifecycle = self.new_lifecycle(adapter)
                with fixture.claimed() as (coordinator, _):
                    lifecycle.prepare(coordinator, "run-1")
                    self.rejected_or_held(lambda: lifecycle.fixture_check(coordinator, "run-1"))
                    self.assertEqual(fixture.run()["state"], "local-held")
                    self.assertNotIn("poll_command", adapter.names())
                    for call in adapter.arguments("stop"):
                        self.assertFalse(contains_identity(call["commands"], "sh_foreign"))

    def test_explicit_timeout_and_killed_poll_results_never_pass(self):
        for status in ("timeout", "killed"):
            with self.subTest(status=status), W2Fixture() as fixture:
                adapter = FakeAdapter(self.clock)
                adapter.polls.append({"status": status, "exit": None, "progress": False})
                lifecycle = self.new_lifecycle(adapter)
                with fixture.claimed() as (coordinator, _):
                    lifecycle.prepare(coordinator, "run-1")
                    result = lifecycle.fixture_check(coordinator, "run-1")
                    self.assertEqual(result["run"]["state"], "local-failed")
                    self.assertLess(adapter.names().index("collect"), adapter.names().index("stop"))

    def test_idle_before_live_command_cannot_be_extended_by_adapter_heartbeats(self):
        self.adapter.delays["qualify"] = 6
        with self.fixture.claimed() as (coordinator, _):
            self.rejected_or_held(lambda: self.execute(coordinator))
            self.assertNotIn("create_session", self.adapter.names())
            self.assertNotIn("start_command", self.adapter.names())
            self.assert_no_integration()

    def test_late_collection_or_stop_confirmation_is_held_without_repeating_cleanup(self):
        for method in ("collect", "stop"):
            with self.subTest(method=method), W2Fixture() as fixture:
                adapter = FakeAdapter(self.clock)
                adapter.delays[method] = 61
                lifecycle = self.new_lifecycle(adapter)
                with fixture.claimed() as (coordinator, _):
                    lifecycle.prepare(coordinator, "run-1")
                    self.rejected_or_held(lambda: lifecycle.fixture_check(coordinator, "run-1"))
                    self.assertEqual(fixture.run()["state"], "local-held")
                    self.assertEqual(len(adapter.arguments(method)), 1)
                    calls = deepcopy(adapter.calls)
                    self.assertTrue(lifecycle.fixture_check(coordinator, "run-1")["existing"])
                    self.assertEqual(adapter.calls, calls)

    def test_diagnostic_byte_and_counter_bounds_reject_without_exporting_canary(self):
        values = ({"diagnostics": [{"code": "W2_SECRET_CANARY", "count": 1}]},
                  {"diagnostics": [{"code": "output_omitted", "count": True}]},
                  {"diagnostics": [{"code": "output_omitted", "count": -1}]},
                  {"diagnostics": [{"code": "output_omitted", "count": 1}] * 3000})
        for value in values:
            with self.subTest(kind=len(canonical(value))), W2Fixture() as fixture:
                adapter = FakeAdapter(self.clock)
                adapter.responses["collect"] = value
                lifecycle = self.new_lifecycle(adapter)
                with fixture.claimed() as (coordinator, _):
                    lifecycle.prepare(coordinator, "run-1")
                    self.rejected_or_held(lambda: lifecycle.fixture_check(coordinator, "run-1"))
                    self.assertEqual(fixture.run()["state"], "local-held")
                    self.assertNotIn("W2_SECRET_CANARY", json.dumps(fixture.store.read()))
                    for evidence in Path(fixture.run()["local"]["artifact"]).glob("evidence/*.json"):
                        self.assertNotIn(b"W2_SECRET_CANARY", evidence.read_bytes())

    def test_existing_owner_derived_artifact_is_retained_not_adopted_or_deleted(self):
        destination = self.fixture.store.root / "artifacts" / ("local-" + digest(b"project/run-1"))
        with self.fixture.claimed() as (coordinator, _):
            destination.mkdir()
            canary = destination / "unowned-existing-canary"
            canary.write_bytes(b"do not adopt or remove\n")
            self.rejected_or_held(lambda: self.prepare(coordinator))
            self.assertEqual(self.fixture.run()["state"], "local-held")
            self.assertEqual(canary.read_bytes(), b"do not adopt or remove\n")
            self.assertEqual(self.adapter.calls, [])
            self.assert_held_repeat_has_no_effects_or_budget_reset(coordinator)

    def test_stop_requested_before_preparation_never_creates_checkout_or_runtime(self):
        with self.fixture.claimed() as (coordinator, _):
            stop = self.fixture.launcher.local_stop("project", "feature", "run-1")
            self.assertEqual(stop["run"]["state"], "local-held")
            self.assertIsNone(stop["run"]["local"]["runtime_started_at"])
            self.assertIsNone(stop["run"]["local"]["prepared"])
            self.assertEqual(self.prepare(coordinator)["run"]["state"], "local-held")
            self.assertEqual(self.check(coordinator)["run"]["state"], "local-held")
            self.assertEqual(self.adapter.calls, [])

    def test_coordinator_token_fencing_prevents_further_runtime_effects(self):
        def fence(arguments):
            self.fixture.mutate_ledger(lambda ledger: ledger["features"]["project/feature"]["coordinator"].update(token="replacement-token"))
        self.adapter.hooks["qualify"] = fence
        with self.fixture.claimed() as (coordinator, _):
            try:
                self.execute(coordinator)
            except RoutineError:
                pass
            self.assertEqual(self.fixture.feature()["coordinator"]["token"], "replacement-token")
            self.assertNotIn("create_session", self.adapter.names())
            self.assertNotIn("start_command", self.adapter.names())
            self.assert_no_integration()

    def test_kernel_driver_crash_preserves_checkpoint_budget_and_blocks_automatic_takeover(self):
        # Actual interpreter exit tests OS lease release and durable intent. All
        # runtime calls inside the child are FakeAdapter; only fixture Git runs.
        script = """
import json, os, sys
from w2_fixture import FakeAdapter, FakeClock
from routine.launcher import Launcher
from routine.local_lifecycle import LocalLifecycle
from routine.store import Store
store = Store(sys.argv[1])
launcher = Launcher(store)
clock = FakeClock()
adapter = FakeAdapter(clock)
def crash(arguments):
    os._exit(42)
adapter.hooks[sys.argv[4]] = crash
with launcher.coordinator('project', 'feature', 'fixture-crashed-driver') as coord:
    coord.claim_local('01', 'run-1', sys.argv[2], 'dispatch-1', json.loads(sys.argv[3]))
    lifecycle = LocalLifecycle(adapter, clock=clock.time, monotonic=clock.monotonic, sleep=clock.sleep)
    lifecycle.prepare(coord, 'run-1')
    lifecycle.fixture_check(coord, 'run-1')
"""
        for method in ("qualify", "create_session", "start_command", "collect", "stop"):
            with self.subTest(method=method), W2Fixture() as fixture:
                authorization = fixture.approved()
                env = fixture.env()
                env["PYTHONPATH"] += os.pathsep + str(Path(__file__).parent)
                result = subprocess.run([sys.executable, "-B", "-c", script, str(fixture.store.root),
                                         authorization, json.dumps(fixture.manifest["baseline"]), method],
                                        env=env, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 42, result.stdout + result.stderr)
                before = fixture.run()
                self.assertIn(before["state"], ("local-starting", "local-running", "local-stopping"))
                self.assertEqual(before["local"]["checkpoints"][-1]["phase"], "intent")
                self.assertTrue(Path(before["local"]["prepared"]["checkout"]).is_dir())
                with self.assertRaises(RoutineError) as caught:
                    with fixture.launcher.coordinator("project", "feature", "unauthorized-replacement"):
                        self.fail("Implicit crash recovery admitted")
                self.assertEqual(caught.exception.code, "recovery_required")
                stopped = fixture.launcher.local_stop("project", "feature", "run-1")["run"]
                self.assertEqual(stopped["state"], "local-held")
                for key in ("runtime_started_at", "runtime_deadline", "checkpoints", "prepared"):
                    self.assertEqual(stopped["local"][key], before["local"][key])
                self.assertEqual(stopped["budgets"], before["budgets"])
                self.assertNotEqual(stopped.get("result", {}).get("outcome"), "fixture-passed")

    def test_typed_coordinator_entrypoints_use_only_injected_adapter_and_existing_claim(self):
        self.fixture.launcher = Launcher(self.fixture.store, local_adapter=self.adapter)
        with self.fixture.claimed() as (coordinator, _):
            prepared = coordinator.local_prepare("run-1")
            self.assertEqual(prepared["run"]["state"], "local-prepared")
            result = coordinator.local_fixture_check("run-1")
            self.assertEqual(result["run"]["state"], "local-fixture-passed")
            self.assertEqual(result["run"]["result"]["qualification"], "deterministic")
            calls = deepcopy(self.adapter.calls)
            self.assertTrue(coordinator.local_fixture_check("run-1")["existing"])
            self.assertTrue(coordinator.local_prepare("run-1")["existing"])
            stopped = coordinator.local_stop("run-1")
            self.assertEqual(stopped["run"]["state"], "local-fixture-passed")
            self.assertEqual(self.adapter.calls, calls)
            self.assertEqual(set(self.fixture.store.read()["runs"]), {"project/run-1"})
            self.assert_no_integration()

    def test_held_driver_retains_feature_capacity_and_waiting_does_not_start_or_reset_budgets(self):
        self.fixture.profile["concurrency"]["workers_per_feature"] = 1
        self.fixture.save_profile()
        self.adapter.responses["qualify"] = OSError("Fixture response unavailable; no runtime launch")
        with self.fixture.claimed() as (coordinator, _):
            self.rejected_or_held(lambda: self.execute(coordinator))
            first = deepcopy(self.fixture.run())
            self.assertEqual(first["state"], "local-held")
            self.assertIsNotNone(first["local"]["driver"])
            self.fixture.claim(coordinator, slice_id="03", run_id="run-2", dispatch_id="dispatch-2")
            before = self.fixture.run("run-2")
            calls = deepcopy(self.adapter.calls)
            for _ in range(2):
                with self.assertRaises(RoutineError) as caught:
                    self.lifecycle.prepare(coordinator, "run-2")
                self.assertEqual(caught.exception.code, "capacity_wait")
                self.clock.advance(5)
            self.assertEqual(self.fixture.run("run-2"), before)
            self.assertEqual(self.fixture.run(), first)
            self.assertEqual(self.adapter.calls, calls)
            destination = self.fixture.store.root / "artifacts" / ("local-" + digest(b"project/run-2"))
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
