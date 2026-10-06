"""Offline local fixtures and injected administration; no Docker/privilege proof."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import json
import os
import unittest

import test_m2_retention as fixture
from routine.contracts import RoutineError, canonical
from routine.retention import production_inspection
from routine.retention_helper import OneShotInspection, PROBE_FLAGS
from routine.retention_lifecycle import (CollectedInspection, HandoffReceipt, InspectionLimits,
    InspectionPrerequisites, InspectionRequest, InspectorObservation, InspectorStop, MountIdentity,
    SourceLease, StorageObservation)


class Authority:
    def __init__(self, test):
        self.test = test
        self.lease_active = False
        self.proof = SourceLease(True, True)

    @contextmanager
    def source_lease(self, request, timeout):
        self.test.hit("source_lease", timeout)
        self.test.assertEqual(request, self.test.request)
        self.lease_active = True
        try:
            yield self.proof
        finally:
            self.test.events.append("lease-closed")
            self.lease_active = False

    def read_run(self, request, timeout):
        self.test.hit("read_run", timeout)
        self.test.assertTrue(self.lease_active)
        self.test.assertEqual(request, self.test.request)
        return self.test.run


class Adapter:
    def __init__(self, test):
        self.test = test
        self.proof = InspectionPrerequisites(test.identity, True)
        self.inspector_id = "1" * 64
        self.handoff_receipt = None
        self.spec = None
        self.collected = None
        self.stop_receipt = None
        self.release_result = True
        self.observation = None

    def preflight(self, binding, identity, timeout):
        self.test.hit("preflight", timeout)
        return self.proof

    def read_source(self, binding, container_id, timeout):
        self.test.hit("read_source", timeout)
        self.test.assertEqual(container_id, self.test.run["container_id"])
        return deepcopy(self.test.info), deepcopy(self.test.value)

    @contextmanager
    def pin_storage(self, binding, timeout):
        self.test.hit("pin_storage", timeout)
        self.test.assertTrue(self.test.authority.lease_active)
        self.test.storage_active = True
        descriptor = os.dup(self.test.fd)
        try:
            # This fixture observer is injected, not actual privileged xattr proof.
            yield StorageObservation(descriptor, os.geteuid(), lambda fd: [])
        finally:
            os.close(descriptor)
            self.test.storage_active = False
            self.test.events.append("storage-closed")

    def handoff(self, checkout_fd, identity, nonce, timeout):
        self.test.hit("handoff", timeout)
        self.test.assertEqual(MountIdentity.from_descriptor(checkout_fd), identity)
        self.test.assertTrue(self.test.storage_active)
        self.test.assertEqual(identity.inode, self.test.project.stat().st_ino)
        receipt = HandoffReceipt("2" * 64, identity, "/run/routine-inspection/fixture", True, True, True, "rprivate")
        return self.handoff_receipt or receipt

    def create_inspector(self, spec, handoff, timeout):
        self.test.hit("create_inspector", timeout)
        self.test.assertEqual(self.test.records[-1]["state"], "create-intent")
        self.spec = spec
        return self.inspector_id

    def verify_inspector(self, spec, container_id, handoff, timeout):
        self.test.hit("verify_inspector", timeout)
        return self.observation or InspectorObservation(container_id, spec.nonce, spec.configuration_sha256, handoff.token)

    def start_inspector(self, spec, container_id, timeout):
        self.test.hit("start_inspector", timeout)
        self.test.assertEqual(self.test.records[-1]["state"], "start-intent")

    def collect(self, spec, container_id, max_bytes, timeout):
        self.test.hit("collect", timeout)
        self.test.assertEqual(max_bytes, self.test.limits.max_evidence_bytes)
        value = {"version": 1, "source_container_id": spec.source_container_id,
                 "source_checkpoint_sha256": spec.source_checkpoint_sha256, "inspector_container_id": container_id,
                 "inspector_nonce": spec.nonce, "baseline_commit": spec.baseline_commit,
                 "repository_code_executed": False, **{key: True for key in PROBE_FLAGS}}
        return self.collected or CollectedInspection(container_id, spec.nonce, 0, canonical(value))

    def stop_confirmed(self, spec, container_id, timeout):
        self.test.hit("stop_confirmed", timeout)
        self.test.assertTrue(self.test.storage_active)
        self.test.assertTrue(self.test.authority.lease_active)
        return self.stop_receipt or InspectorStop(container_id, spec.nonce, True)

    def release_handoff(self, receipt, timeout):
        self.test.hit("release_handoff", timeout)
        self.test.assertTrue(self.test.authority.lease_active)
        return self.release_result


class InspectionLifecycleTests(unittest.TestCase):
    def setUp(self):
        fixture.RetentionTests.setUp(self)
        self.request = InspectionRequest("project-1", "feature-1", "run-1")
        self.run.update(request=self.request.as_dict(), baseline={"commit": "a" * 40})
        self.identity = MountIdentity.from_descriptor(self.fd)
        self.events, self.records, self.timeouts = [], [], []
        self.time = 0
        self.storage_active = False
        self.faults = {}
        self.limits = InspectionLimits()
        self.authority = Authority(self)
        self.adapter = Adapter(self)
        self.fail_journal_states = set()

    def hit(self, event, timeout):
        self.events.append(event)
        self.timeouts.append((event, timeout))
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 15)
        fault = self.faults.get(event)
        if callable(fault):
            fault(timeout)
        elif fault is not None:
            raise fault

    def sink(self, record):
        if record["state"] in self.fail_journal_states:
            raise OSError("private-journal-canary")
        self.records.append(deepcopy(record))

    def helper(self, **values):
        return OneShotInspection(self.binding, self.identity, authority=self.authority, checkpoint_sink=self.sink,
                                 adapter=values.pop("adapter", self.adapter), limits=self.limits,
                                 trusted_owner_uid=os.geteuid(), clock=lambda: self.time,
                                 nonce_factory=lambda: "3" * 32, **values)

    def inspect(self):
        baseline = deepcopy(self.run)
        before = fixture.RetentionTests.fd_count()
        result = self.helper().inspect(self.request)
        self.assertEqual(self.run, baseline)
        self.assertEqual(fixture.RetentionTests.fd_count(), before)
        self.assertFalse(self.authority.lease_active)
        self.assertFalse(self.storage_active)
        self.assertFalse(result.qualified)
        return result

    def test_positive_fixed_probe_lifecycle_journal_and_baseline_independence(self):
        result = self.inspect()
        self.assertEqual(result.outcome, "inspection-passed")
        self.assertTrue(result.stop_confirmed and result.handoff_release_confirmed and result.source_unchanged)
        self.assertEqual(self.events[-4:], ["read_source", "release_handoff", "storage-closed", "lease-closed"])
        states = [record["state"] for record in self.records]
        self.assertLess(states.index("create-intent"), states.index("created"))
        self.assertEqual(self.records[-1]["result"]["scan_counts"], {"entries": 3, "logical_bytes": 29})
        self.assertEqual(self.records[-1]["work_deadline"], 60)
        self.assertEqual(self.records[-1]["cleanup_deadline"], 20)
        self.assertEqual(self.records[-1]["inspector_container_id"], self.adapter.inspector_id)
        text = json.dumps(self.records)
        for canary in (str(self.root), "fixture content", "fixture HEAD", "/run/routine-inspection"):
            self.assertNotIn(canary, text)
        self.assertEqual(self.adapter.spec.configuration()["network_mode"], "none")
        self.assertEqual(self.adapter.spec.configuration()["disk_mb"], 64)

    def test_default_adapter_and_production_gate_refuse_before_authority_or_raw_reads(self):
        result = self.helper(adapter=None).inspect(self.request)
        self.assertEqual(result.outcome, "inspection-blocked")
        self.assertEqual(self.events, [])
        with self.assertRaises(RoutineError):
            production_inspection(enabled=True, adapter=self.adapter, uid=0)

    def test_requests_accept_only_identifiers_and_helper_is_one_shot(self):
        for value in ("../run", "/run", "run/name", ""):
            with self.assertRaises(RoutineError):
                InspectionRequest("project-1", "feature-1", value)
        helper = self.helper()
        with self.assertRaises(RoutineError):
            helper.inspect({**self.request.as_dict(), "path": "/foreign"})
        helper.inspect(self.request)
        with self.assertRaises(RoutineError):
            helper.inspect(self.request)

    def test_limits_cannot_be_weakened_or_use_boolean_or_nonfinite_values(self):
        for values in ({"total_seconds": 61}, {"stop_seconds": 21}, {"command_seconds": 16},
                       {"max_entries": 10001}, {"max_depth": 65}, {"max_evidence_bytes": 65537},
                       {"total_seconds": True}, {"total_seconds": float("nan")}, {"max_entries": 0}):
            with self.assertRaises(RoutineError):
                InspectionLimits(**values)

    def test_privileged_visibility_and_mount_proof_required_before_raw_reads(self):
        for proof in (InspectionPrerequisites(self.identity, False), InspectionPrerequisites(self.identity, 1),
                      InspectionPrerequisites(replace(self.identity, mount_id=self.identity.mount_id + 1), True)):
            self.adapter.proof = proof
            self.events.clear()
            result = self.inspect()
            self.assertEqual(result.outcome, "inspection-failed")
            self.assertEqual(self.events, ["preflight"])

    def test_lease_and_external_admin_exclusion_are_required(self):
        for proof in (SourceLease(False, True), SourceLease(True, False), SourceLease(True, 1)):
            self.authority.proof = proof
            self.events.clear()
            result = self.inspect()
            self.assertEqual(result.diagnostic, "recovery_required")
            self.assertNotIn("read_run", self.events)

    def test_other_feature_and_legacy_sources_cannot_be_adopted(self):
        self.run["request"]["feature_id"] = "another-feature"
        self.assertEqual(self.inspect().diagnostic, "unapproved")
        self.run["request"] = self.request.as_dict()
        del self.run["launch_id"]
        self.assertEqual(self.inspect().diagnostic, "recovery_required")
        self.assertNotIn("handoff", self.events)

    def test_raw_scan_failure_never_attempts_handoff(self):
        (self.project / "unsafe").symlink_to("/foreign")
        result = self.inspect()
        self.assertEqual(result.diagnostic, "unsupported_checkout")
        self.assertNotIn("handoff", self.events)

    def test_unapproved_storage_descriptor_is_denied_before_handoff(self):
        original = self.adapter.pin_storage
        @contextmanager
        def changed(binding, timeout):
            with original(binding, timeout) as observation:
                descriptor = os.open(self.project, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    yield replace(observation, descriptor=descriptor)
                finally:
                    os.close(descriptor)
        self.adapter.pin_storage = changed
        result = self.inspect()
        self.assertEqual(result.outcome, "inspection-failed")
        self.assertNotIn("handoff", self.events)

    def test_path_based_proc_fd_or_raw_root_handoff_is_never_accepted(self):
        checkout = MountIdentity(self.project.stat().st_dev, self.project.stat().st_ino, self.identity.mount_id)
        for path in ("/proc/self/fd/4", "/proc/123/fd/4", "/dev/fd/4", str(self.project), "/run/a/../b"):
            self.events.clear()
            self.adapter.handoff_receipt = HandoffReceipt("2" * 64, checkout, path, True, True, True, "rprivate")
            result = self.inspect()
            self.assertEqual(result.outcome, "inspection-held")
            self.assertNotIn("create_inspector", self.events)
            self.assertNotIn("release_handoff", self.events)

    def test_handoff_requires_readonly_nonrecursive_private_identity(self):
        checkout = MountIdentity(self.project.stat().st_dev, self.project.stat().st_ino, self.identity.mount_id)
        receipt = HandoffReceipt("2" * 64, checkout, "/run/routine-inspection/fixture", True, True, True, "rprivate")
        for invalid in (replace(receipt, read_only=False), replace(receipt, nonrecursive=False),
                        replace(receipt, propagation="rshared"), replace(receipt, staging_verified=1),
                        replace(receipt, source_identity=self.identity)):
            self.adapter.handoff_receipt = invalid
            self.assertEqual(self.inspect().outcome, "inspection-held")

    def test_ambiguous_handoff_retains_effects_and_never_creates_inspector(self):
        self.faults["handoff"] = OSError("private-path-canary")
        result = self.inspect()
        self.assertEqual(result.outcome, "inspection-held")
        self.assertFalse(result.handoff_release_confirmed)
        self.assertNotIn("create_inspector", self.events)

    def test_ambiguous_creation_cannot_stop_by_name_or_release_live_handoff(self):
        self.faults["create_inspector"] = OSError("private-creation-canary")
        result = self.inspect()
        self.assertEqual(result.outcome, "inspection-held")
        self.assertIsNone(result.inspector_container_id)
        self.assertNotIn("stop_confirmed", self.events)
        self.assertNotIn("release_handoff", self.events)

    def test_foreign_id_nonce_or_configuration_cannot_authorize_start_or_stop(self):
        for observation in (InspectorObservation("4" * 64, "3" * 32, "0" * 64, "2" * 64),
                            InspectorObservation(self.adapter.inspector_id, "4" * 32, "0" * 64, "2" * 64),
                            InspectorObservation(self.adapter.inspector_id, "3" * 32, "0" * 64, "2" * 64)):
            self.events.clear()
            self.adapter.observation = observation
            result = self.inspect()
            self.assertEqual(result.outcome, "inspection-held")
            self.assertNotIn("start_inspector", self.events)
            self.assertNotIn("stop_confirmed", self.events)

    def test_start_failure_stops_owned_id_and_releases_handoff(self):
        self.faults["start_inspector"] = OSError("private-start-canary")
        result = self.inspect()
        self.assertEqual(result.outcome, "inspection-failed")
        self.assertTrue(result.stop_confirmed and result.handoff_release_confirmed)

    def test_late_success_fails_and_cleanup_uses_reserved_shared_deadline(self):
        def late(timeout):
            self.time += timeout
        self.faults["collect"] = late
        result = self.inspect()
        self.assertEqual(result.diagnostic, "command_timeout")
        self.assertTrue(result.stop_confirmed)
        self.assertEqual(self.records[-1]["cleanup_deadline"], 35)
        self.assertEqual(self.records[-1]["consumed_seconds"], 15)

    def test_context_entry_is_included_in_command_deadline(self):
        self.faults["source_lease"] = lambda timeout: setattr(self, "time", self.time + timeout)
        result = self.inspect()
        self.assertEqual(result.diagnostic, "command_timeout")
        self.assertNotIn("read_run", self.events)

    def test_stop_failure_or_foreign_stop_receipt_holds_handoff(self):
        self.adapter.stop_receipt = InspectorStop("4" * 64, "3" * 32, True)
        result = self.inspect()
        self.assertEqual(result.diagnostic, "stop_unconfirmed")
        self.assertNotIn("release_handoff", self.events)
        self.assertIsNone(result.evidence_sha256)

    def test_release_failure_retains_inspector_and_holds_result(self):
        self.adapter.release_result = 1
        result = self.inspect()
        self.assertEqual(result.diagnostic, "handoff_release_unconfirmed")
        self.assertTrue(result.stop_confirmed)
        self.assertIsNone(result.evidence_sha256)

    def test_source_restart_after_collection_invalidates_success(self):
        original = deepcopy(self.value)
        def restart(timeout):
            self.value["State"]["FinishedAt"] = "changed-after-inspection"
        self.faults["stop_confirmed"] = restart
        result = self.inspect()
        self.assertEqual(result.diagnostic, "recovery_required")
        self.assertFalse(result.source_unchanged)
        self.assertTrue(result.handoff_release_confirmed)
        self.value = original

    def test_unexpected_adapter_errors_export_only_allowlisted_diagnostic(self):
        self.faults["collect"] = ValueError("raw-secret-canary")
        result = self.inspect()
        self.assertEqual(result.diagnostic, "adapter_failed")
        self.assertNotIn("raw-secret-canary", json.dumps(self.records))

    def test_journal_failure_before_creation_prevents_effect_and_releases_handoff(self):
        self.fail_journal_states = {"create-intent"}
        with self.assertRaises(RoutineError) as caught:
            self.helper().inspect(self.request)
        self.assertEqual(caught.exception.code, "inspection_journal_failed")
        self.assertNotIn("create_inspector", self.events)
        self.assertIn("release_handoff", self.events)
        self.assertEqual(self.records[-1]["state"], "inspection-held")

    def test_journal_failure_after_start_still_stops_owned_inspector(self):
        self.fail_journal_states = {"collecting", "stopping"}
        with self.assertRaises(RoutineError):
            self.helper().inspect(self.request)
        self.assertIn("stop_confirmed", self.events)
        self.assertIn("release_handoff", self.events)
        self.assertEqual(self.records[-1]["state"], "inspection-held")

    def test_final_journal_failure_can_never_return_success(self):
        self.fail_journal_states = {"inspection-passed"}
        with self.assertRaises(RoutineError):
            self.helper().inspect(self.request)
        self.assertIn("release_handoff", self.events)

    def test_initial_journal_failure_prevents_even_preflight(self):
        self.fail_journal_states = {"preparing"}
        with self.assertRaises(RoutineError):
            self.helper().inspect(self.request)
        self.assertEqual(self.events, [])

    def test_sink_rejecting_existing_inspection_prevents_duplicate_effects(self):
        first = self.inspect()
        events = list(self.events)
        records = deepcopy(self.records)
        original = self.sink
        def rejecting(record):
            if record["state"] == "preparing":
                raise RoutineError("recovery_required", "existing inspection reservation")
            original(record)
        self.sink = rejecting
        with self.assertRaises(RoutineError):
            self.helper().inspect(self.request)
        self.assertEqual(self.events, events)
        self.assertEqual(self.records, records)
        self.assertEqual(first.outcome, "inspection-passed")

    def test_sink_cannot_mutate_controller_record_via_its_snapshot(self):
        original = self.sink
        def mutating(record):
            original(record)
            record["state"] = "foreign-state"
            record["request"]["run_id"] = "foreign-run"
        self.sink = mutating
        self.assertEqual(self.inspect().outcome, "inspection-passed")
        self.assertEqual(self.records[-1]["request"], self.request.as_dict())

    def test_total_deadline_and_stop_reserve_are_not_reset_after_late_collect(self):
        self.faults["start_inspector"] = lambda timeout: setattr(self, "time", 14)
        # Advance between commands, not inside a command exceeding its own bound.
        original = self.sink
        def advancing(record):
            if record["state"] == "collecting":
                self.time = 59
            original(record)
        self.sink = advancing
        self.faults["collect"] = lambda timeout: setattr(self, "time", self.time + timeout)
        result = self.inspect()
        self.assertEqual(result.outcome, "inspection-failed")
        self.assertEqual(result.diagnostic, "command_timeout")
        self.assertEqual(dict(self.timeouts)["collect"], 1)
        self.assertEqual(self.records[-1]["work_deadline"], 60)
        self.assertEqual(self.records[-1]["cleanup_deadline"], 80)
        self.assertEqual(self.records[-1]["consumed_seconds"], 60)

    def test_late_stop_success_is_not_stop_confirmation(self):
        self.faults["stop_confirmed"] = lambda timeout: setattr(self, "time", self.time + timeout)
        result = self.inspect()
        self.assertEqual(result.outcome, "inspection-held")
        self.assertFalse(result.stop_confirmed)
        self.assertNotIn("release_handoff", self.events)

    def test_foreign_handoff_token_cannot_authorize_inspector_start(self):
        original = self.adapter.verify_inspector
        def foreign(spec, container_id, handoff, timeout):
            return replace(original(spec, container_id, handoff, timeout), handoff_token="4" * 64)
        self.adapter.verify_inspector = foreign
        result = self.inspect()
        self.assertEqual(result.outcome, "inspection-held")
        self.assertNotIn("start_inspector", self.events)
        self.assertNotIn("stop_confirmed", self.events)

    def test_missing_creation_id_cannot_be_replaced_with_a_name(self):
        self.adapter.inspector_id = None
        result = self.inspect()
        self.assertEqual(result.outcome, "inspection-held")
        self.assertIsNone(result.inspector_container_id)
        self.assertNotIn("stop_confirmed", self.events)

    def test_evidence_must_match_exit_and_immutable_collector_identity(self):
        original = self.adapter.collect
        def changed(spec, container_id, max_bytes, timeout):
            return replace(original(spec, container_id, max_bytes, timeout), **self.collector_mutation)
        self.adapter.collect = changed
        for mutation in ({"container_id": "4" * 64}, {"nonce": "4" * 32}, {"exit_code": 1}, {"exit_code": False}):
            self.collector_mutation = mutation
            result = self.inspect()
            self.assertEqual(result.diagnostic, "invalid_evidence")
            self.assertTrue(result.stop_confirmed and result.handoff_release_confirmed)

    def test_lease_release_failure_holds_without_falsifying_handoff_confirmation(self):
        original = self.authority.source_lease
        @contextmanager
        def bad_exit(request, timeout):
            with original(request, timeout) as lease:
                yield lease
            raise OSError("private-lease-canary")
        self.authority.source_lease = bad_exit
        result = self.inspect()
        self.assertEqual(result.diagnostic, "lease_release_unconfirmed")
        self.assertFalse(result.lease_release_confirmed)
        self.assertTrue(result.handoff_release_confirmed)

    def test_configured_storage_owner_cannot_be_selected_by_observer(self):
        original = self.adapter.pin_storage
        @contextmanager
        def wrong_owner(binding, timeout):
            with original(binding, timeout) as observation:
                yield replace(observation, owner_uid=os.geteuid() + 1)
        self.adapter.pin_storage = wrong_owner
        result = self.inspect()
        self.assertEqual(result.diagnostic, "unsafe_storage")
        self.assertNotIn("handoff", self.events)

    def test_interruption_stops_then_releases_then_closes_descriptors(self):
        self.faults["collect"] = KeyboardInterrupt()
        before = fixture.RetentionTests.fd_count()
        with self.assertRaises(KeyboardInterrupt):
            self.helper().inspect(self.request)
        self.assertEqual(fixture.RetentionTests.fd_count(), before)
        self.assertEqual(self.records[-1]["state"], "inspection-failed")
        self.assertIn("stop_confirmed", self.events)
        self.assertIn("release_handoff", self.events)

    def test_interrupt_during_cleanup_journal_cannot_skip_stop_or_descriptor_cleanup(self):
        original = self.sink
        def interrupted(record):
            if record["state"] in ("stopping", "releasing-handoff"):
                raise KeyboardInterrupt()
            original(record)
        self.sink = interrupted
        before = fixture.RetentionTests.fd_count()
        with self.assertRaises(KeyboardInterrupt):
            self.helper().inspect(self.request)
        self.assertEqual(fixture.RetentionTests.fd_count(), before)
        self.assertIn("stop_confirmed", self.events)
        self.assertIn("release_handoff", self.events)
        self.assertEqual(self.records[-1]["state"], "inspection-held")
        self.assertFalse(self.authority.lease_active)

    def test_malformed_raw_extra_boolean_forged_and_oversized_evidence_fail(self):
        original = self.adapter.collect
        def bad_collect(spec, container_id, max_bytes, timeout):
            good = original(spec, container_id, max_bytes, timeout)
            value = json.loads(good.evidence)
            mutation = self.evidence_mutation
            if isinstance(mutation, bytes):
                return replace(good, evidence=mutation)
            mutation(value)
            return replace(good, evidence=canonical(value))
        self.adapter.collect = bad_collect
        for mutation in (b"private-raw-canary", b"{}\n{}", b'{"version":1,"version":1}', b"x" * 65537,
                         lambda value: value.update(raw_output="raw-secret-canary"),
                         lambda value: value.update(mount_read_only=1),
                         lambda value: value.update(inspector_nonce="0" * 32),
                         lambda value: value.update(repository_code_executed=True)):
            self.evidence_mutation = mutation
            result = self.inspect()
            self.assertEqual(result.outcome, "inspection-failed")
            self.assertTrue(result.stop_confirmed and result.handoff_release_confirmed)
            self.assertNotIn("raw-secret-canary", json.dumps(self.records))


if __name__ == "__main__":
    unittest.main()
