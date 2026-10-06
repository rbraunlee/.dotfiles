"""Bounded one-shot component; authority, journal and side effects are injected.

No administrative entry point or real mount/Docker adapter is provided. The
checkpoint sink must atomically retain a dedicated inspection record, reject
conflicting/repeated inspection IDs and hold dispatch for unfinished/held records.
It must never write the source baseline record. All adapter timeouts are contracts
for a killable, bounded transport; this in-process model cannot kill a hung adapter.
"""
from contextlib import ExitStack
from copy import deepcopy
import re
import secrets
import time

from .contracts import RoutineError, digest, hash_value, parse_json, require
from .retention import (StorageBinding, confirm_source_unchanged, pin_raw_checkout,
                        source_from_inspection)
from .retention_lifecycle import (CollectedInspection, DisabledInspectionAdapter, HandoffReceipt,
                                 InspectionLimits, InspectionPrerequisites, InspectionRequest,
                                 InspectionResult, InspectorObservation, InspectorSpec, InspectorStop,
                                 MountIdentity, SourceLease, StorageObservation)


DIAGNOSTICS = {"storage_inspection_unavailable", "unsafe_storage", "unsupported_checkout",
               "recovery_required", "invalid_runtime", "invalid_input", "input_limit", "command_timeout",
               "unapproved", "coordinator_busy", "disk_quota_unavailable", "invalid_evidence",
               "inspection_journal_failed"}
PROBE_FLAGS = {"head_and_run_branch_verified", "git_metadata_independent", "git_object_connectivity_verified",
               "mount_read_only", "write_denied_with_erofs", "network_loopback_only", "docker_socket_absent"}


class OneShotInspection:
    def __init__(self, binding, trusted_mount_identity, *, authority, checkpoint_sink, adapter=None,
                 limits=None, trusted_owner_uid=0, clock=time.monotonic,
                 nonce_factory=lambda: secrets.token_hex(16)):
        require(isinstance(binding, StorageBinding) and isinstance(trusted_mount_identity, MountIdentity),
                "invalid_runtime", "Inspection requires a trusted administrative binding")
        self.binding, self.mount_identity = binding, trusted_mount_identity
        self.authority, self.sink = authority, checkpoint_sink
        self.adapter = adapter if adapter is not None else DisabledInspectionAdapter()
        self.limits = limits if limits is not None else InspectionLimits()
        require(isinstance(self.limits, InspectionLimits) and callable(checkpoint_sink),
                "invalid_input", "Invalid inspection component configuration")
        self.clock, self.nonce_factory = clock, nonce_factory
        require(type(trusted_owner_uid) is int and trusted_owner_uid >= 0,
                "invalid_runtime", "Invalid administrative storage owner")
        self.owner_uid = trusted_owner_uid
        self.used = False

    def inspect(self, request):
        require(isinstance(request, InspectionRequest), "invalid_input", "Inspection accepts identifiers only")
        require(not self.used, "recovery_required", "One-shot inspection cannot be retried or resumed")
        self.used = True
        nonce = self.nonce_factory()
        require(isinstance(nonce, str) and re.fullmatch(r"[0-9a-f]{32}", nonce),
                "invalid_runtime", "Invalid private inspector preparation identity")
        started = self.clock()
        work_deadline = started + self.limits.total_seconds
        record = {"version": 1, "inspection_id": nonce, "state": "preparing", "request": request.as_dict(),
                  "source_container_id": None, "source_checkpoint_sha256": None, "inspector_nonce": nonce,
                  "inspector_container_id": None, "started_monotonic": started, "work_deadline": work_deadline,
                  "cleanup_deadline": None, "consumed_seconds": 0, "stop_confirmed": True,
                  "handoff_confirmed": False, "handoff_release_confirmed": True, "source_unchanged": False,
                  "lease_release_confirmed": False,
                  "result": None}
        journal_failed = journal_reserved = False

        def journal(state, **values):
            nonlocal journal_failed, journal_reserved
            record.update(values, state=state, consumed_seconds=max(0, self.clock() - started))
            try:
                self.sink(deepcopy(record))
                journal_reserved = True
            except Exception as exc:
                journal_failed = True
                raise RoutineError("inspection_journal_failed", "Inspection checkpoint could not be retained") from exc

        def invoke(operation, *args, deadline=work_deadline):
            now = self.clock()
            require(now < deadline, "command_timeout", "Inspection deadline exhausted")
            timeout = min(self.limits.command_seconds, deadline - now)
            value = operation(*args, timeout)
            require(self.clock() < now + timeout, "command_timeout", "Inspection command exceeded its deadline")
            return value

        def enter(operation, *args):
            now = self.clock()
            value = stack.enter_context(invoke(operation, *args))
            require(self.clock() < min(work_deadline, now + self.limits.command_seconds),
                    "command_timeout", "Inspection lease/storage admission exceeded its deadline")
            return value

        def check_storage(storage):
            require(MountIdentity.from_descriptor(storage.descriptor) == self.mount_identity,
                    "unsafe_storage", "Storage descriptor differs from the approved mount identity")

        def read_source(run):
            value = invoke(self.adapter.read_source, self.binding, run["container_id"])
            require(isinstance(value, tuple) and len(value) == 2,
                    "invalid_runtime", "Malformed storage inspection response")
            return source_from_inspection(self.binding, value[0], value[1], run)

        stack = ExitStack()
        handoff = spec = container_id = source = run = storage = None
        handoff_attempted = inspector_attempted = owned = ready = False
        stopped = released = True
        source_unchanged = lease_closed = False
        evidence = None
        counts = None
        diagnostic = interrupted = None
        try:
            journal("preparing")
            proof = invoke(self.adapter.preflight, self.binding, self.mount_identity)
            require(isinstance(proof, InspectionPrerequisites) and proof.privileged_xattrs is True and
                    proof.mount_identity == self.mount_identity,
                    "unsafe_storage", "Privileged xattr visibility and approved mount identity are required")
            lease = enter(self.authority.source_lease, request)
            require(isinstance(lease, SourceLease) and lease.cooperative is True and lease.external_admin_excluded is True,
                    "recovery_required", "Inspection requires a source lease and external administration exclusion")
            run = deepcopy(invoke(self.authority.read_run, request))
            require(isinstance(run, dict) and isinstance(run.get("request"), dict) and
                    all(run["request"].get(key) == value for key, value in request.as_dict().items()),
                    "unapproved", "Source run differs from requested identifiers")
            hash_value(run.get("container_id"))
            source = read_source(run)
            baseline = run.get("baseline")
            require(isinstance(baseline, dict) and isinstance(baseline.get("commit"), str) and
                    re.fullmatch(r"[0-9a-f]{40}", baseline["commit"]),
                    "invalid_runtime", "Missing approved inspection baseline")
            journal("source-admitted", source_container_id=source.container_id,
                    source_checkpoint_sha256=source.checkpoint_sha256)
            storage = enter(self.adapter.pin_storage, self.binding)
            require(isinstance(storage, StorageObservation) and storage.owner_uid == self.owner_uid and
                    type(storage.owner_uid) is int and callable(storage.xattrs),
                    "unsafe_storage", "Missing privileged storage observer")
            check_storage(storage)
            checkout_fd, counts = stack.enter_context(pin_raw_checkout(
                storage.descriptor, source, owner_uid=storage.owner_uid, deadline=work_deadline,
                max_entries=self.limits.max_entries, max_depth=self.limits.max_depth,
                xattrs=storage.xattrs, clock=self.clock))
            checkout_identity = MountIdentity.from_descriptor(checkout_fd)
            confirm_source_unchanged(source, read_source(run))
            check_storage(storage)
            journal("handoff-intent", handoff_release_confirmed=False)
            handoff_attempted, released = True, False
            handoff = invoke(self.adapter.handoff, checkout_fd, checkout_identity, nonce)
            require(isinstance(handoff, HandoffReceipt), "unsafe_storage", "Missing descriptor handoff receipt")
            handoff.validate(checkout_identity, self.binding.root)
            check_storage(storage)
            confirm_source_unchanged(source, read_source(run))
            journal("handoff-ready", handoff_confirmed=True)
            spec = InspectorSpec(run["runtime_image"], baseline["commit"], "refs/heads/routine/" + request.run_id,
                                 nonce, source.container_id, source.checkpoint_sha256)
            journal("create-intent", stop_confirmed=False)
            inspector_attempted, stopped = True, False
            container_id = invoke(self.adapter.create_inspector, spec, handoff)
            hash_value(container_id)
            # Retain the returned ID before verification/start. Verification failure
            # must not authorize stopping an unrelated/foreign container.
            journal("created", inspector_container_id=container_id)
            observation = invoke(self.adapter.verify_inspector, spec, container_id, handoff)
            require(isinstance(observation, InspectorObservation) and observation.container_id == container_id and
                    observation.nonce == nonce and observation.configuration_sha256 == spec.configuration_sha256 and
                    observation.handoff_token == handoff.token,
                    "recovery_required", "Inspector ownership or effective configuration differs")
            owned = True
            journal("start-intent")
            invoke(self.adapter.start_inspector, spec, container_id)
            journal("collecting")
            collected = invoke(self.adapter.collect, spec, container_id, self.limits.max_evidence_bytes)
            evidence = self._evidence(collected, spec, container_id)
            ready = True
        except (RoutineError, OSError) as exc:
            diagnostic = self._diagnostic(exc)
        except Exception:
            diagnostic = "adapter_failed"
        except BaseException as exc:
            diagnostic, interrupted = "interrupted", exc
        finally:
            cleanup_deadline = min(self.clock() + self.limits.stop_seconds,
                                   work_deadline + self.limits.stop_seconds)
            record["cleanup_deadline"] = cleanup_deadline
            if inspector_attempted and owned:
                try:
                    journal("stopping")
                except BaseException as exc:
                    diagnostic = "inspection_journal_failed"
                    journal_failed = True
                    if not isinstance(exc, Exception):
                        interrupted = interrupted or exc
                try:
                    confirmation = invoke(self.adapter.stop_confirmed, spec, container_id, deadline=cleanup_deadline)
                    stopped = (isinstance(confirmation, InspectorStop) and confirmation.container_id == container_id and
                               confirmation.nonce == nonce and confirmation.stopped is True)
                except BaseException as exc:
                    stopped = False
                    if not isinstance(exc, Exception):
                        interrupted = interrupted or exc
            if source is not None and stopped:
                try:
                    # Source validation after stop uses the reserved cleanup budget.
                    current_run = invoke(self.authority.read_run, request, deadline=cleanup_deadline)
                    require(current_run == run, "recovery_required", "Durable source changed during inspection")
                    rows = invoke(self.adapter.read_source, self.binding, source.container_id, deadline=cleanup_deadline)
                    require(isinstance(rows, tuple) and len(rows) == 2, "invalid_runtime", "Malformed source recheck")
                    confirm_source_unchanged(source, source_from_inspection(self.binding, rows[0], rows[1], run))
                    if storage is not None:
                        check_storage(storage)
                    source_unchanged = True
                except BaseException as exc:
                    diagnostic = self._diagnostic(exc) if isinstance(exc, (RoutineError, OSError)) else "adapter_failed"
                    if not isinstance(exc, Exception):
                        interrupted = interrupted or exc
            if handoff_attempted and stopped and isinstance(handoff, HandoffReceipt):
                try:
                    # A malformed receipt does not authorize cleanup at an attacker-
                    # supplied path. A handoff adapter must retain ambiguous effects.
                    handoff.validate(checkout_identity, self.binding.root)
                    try:
                        journal("releasing-handoff", stop_confirmed=stopped)
                    except BaseException as exc:
                        diagnostic = "inspection_journal_failed"
                        journal_failed = True
                        if not isinstance(exc, Exception):
                            interrupted = interrupted or exc
                    released = invoke(self.adapter.release_handoff, handoff, deadline=cleanup_deadline) is True
                except BaseException as exc:
                    released = False
                    if not isinstance(exc, Exception):
                        interrupted = interrupted or exc
            try:
                stack.close()
                lease_closed = self.clock() < cleanup_deadline
            except BaseException as exc:
                diagnostic = "lease_release_unconfirmed"
                if not isinstance(exc, Exception):
                    interrupted = interrupted or exc

        if not journal_reserved:
            # A rejected/ambiguous initial reservation grants no authority to
            # overwrite an existing inspection with our failure/result record.
            if interrupted is not None:
                raise interrupted
            raise RoutineError("inspection_journal_failed", "Inspection reservation was not confirmed")
        if not stopped or not released or not lease_closed:
            state = "inspection-held"
            diagnostic = ("stop_unconfirmed" if not stopped else
                          "handoff_release_unconfirmed" if not released else "lease_release_unconfirmed")
        elif ready and diagnostic is None and source_unchanged and not journal_failed:
            state = "inspection-passed"
        else:
            state = "inspection-blocked" if diagnostic == "storage_inspection_unavailable" else "inspection-failed"
        if journal_failed:
            state, diagnostic = "inspection-held", "inspection_journal_failed"
        result = InspectionResult(nonce, state, diagnostic, record["inspector_container_id"], stopped, released, lease_closed,
                                  source_unchanged, digest(evidence) if state == "inspection-passed" else None)
        journal(state, stop_confirmed=stopped, handoff_release_confirmed=released,
                lease_release_confirmed=lease_closed, source_unchanged=source_unchanged, result={**result.__dict__,
                    "scan_counts": counts if state == "inspection-passed" else None})
        if interrupted is not None:
            raise interrupted
        if journal_failed:
            raise RoutineError("inspection_journal_failed", "Inspection journal requires administrative reconciliation")
        return result

    @staticmethod
    def _diagnostic(exc):
        if isinstance(exc, RoutineError):
            return exc.code if isinstance(exc.code, str) and exc.code in DIAGNOSTICS else "adapter_failed"
        return "io_error"

    def _evidence(self, collected, spec, container_id):
        require(isinstance(collected, CollectedInspection) and collected.container_id == container_id and
                collected.nonce == spec.nonce and type(collected.exit_code) is int and collected.exit_code == 0 and
                isinstance(collected.evidence, bytes), "invalid_evidence", "Inspector result identity/exit mismatch")
        data = collected.evidence
        require(0 < len(data) <= self.limits.max_evidence_bytes, "input_limit", "Inspection evidence exceeds its bound")
        value = parse_json(data)
        keys = {"version", "source_container_id", "source_checkpoint_sha256", "inspector_container_id",
                "inspector_nonce", "baseline_commit", "repository_code_executed"} | PROBE_FLAGS
        require(isinstance(value, dict) and set(value) == keys and type(value["version"]) is int and
                value["version"] == 1 and value["source_container_id"] == spec.source_container_id and
                value["source_checkpoint_sha256"] == spec.source_checkpoint_sha256 and
                value["inspector_container_id"] == container_id and value["inspector_nonce"] == spec.nonce and
                value["baseline_commit"] == spec.baseline_commit and value["repository_code_executed"] is False and
                all(value[key] is True for key in PROBE_FLAGS),
                "invalid_evidence", "Inspection evidence is missing, forged or contains unapproved fields")
        return data
