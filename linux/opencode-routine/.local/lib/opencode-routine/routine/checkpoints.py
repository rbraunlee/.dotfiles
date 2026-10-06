"""Host-ledger sinks for injected M2 components; no activation or recovery API."""
from contextlib import contextmanager
from copy import deepcopy
import time

from .contracts import canonical, digest, hash_value, require
from .retention_lifecycle import InspectionRequest, SourceLease


class InspectionLedger:
    """Dedicated records, immutable source reads and cooperative source exclusion.

    The maintenance verifier is trusted administration, not a request flag. The
    default denies external-admin exclusion. This does not install a root helper.
    """
    def __init__(self, store, request, maintenance_verifier=None, clock=time.monotonic):
        require(isinstance(request, InspectionRequest), "invalid_input", "Expected inspection identifiers")
        self.store, self.request = store, request
        self.maintenance_verifier, self.clock = maintenance_verifier, clock
        self.inspection_id = None

    def __call__(self, record):
        require(isinstance(record, dict) and record.get("request") == self.request.as_dict() and
                len(canonical(record)) <= 131072, "invalid_input", "Invalid inspection checkpoint")
        nonce = record.get("inspection_id")
        require(isinstance(nonce, str) and len(nonce) == 32 and all(c in "0123456789abcdef" for c in nonce),
                "invalid_input", "Invalid inspection identity")
        with self.store.lock("ledger.lock", blocking=False):
            ledger = self.store.read()
            records = ledger.setdefault("inspections", {})
            if self.inspection_id is None:
                require(record.get("state") == "preparing" and nonce not in records and
                        not any(value.get("request") == record["request"] for value in records.values()),
                        "recovery_required", "Existing retained inspection requires deliberate reconciliation")
            else:
                require(nonce == self.inspection_id and nonce in records and
                        records[nonce].get("request") == record["request"] and
                        records[nonce].get("state") not in ("inspection-passed", "inspection-failed", "inspection-blocked", "inspection-held"),
                        "recovery_required", "Inspection checkpoint cannot replace terminal or unrelated work")
            records[nonce] = deepcopy(record)
            self.store.write(ledger)
            self.inspection_id = nonce

    def read_run(self, request, timeout):
        require(request == self.request and type(timeout) in (float, int) and timeout > 0,
                "unapproved", "Inspection source request differs")
        deadline = self.clock() + timeout
        with self.store.lock("ledger.lock", blocking=False):
            ledger = self.store.read()
            run = ledger["runs"].get(request.project_id + "/" + request.run_id)
            require(isinstance(run, dict) and all(run.get("request", {}).get(key) == value
                    for key, value in request.as_dict().items()), "unapproved", "No matching durable source run")
            value = deepcopy(run)
        require(self.clock() < deadline, "command_timeout", "Source read exceeded its deadline")
        return value

    @contextmanager
    def source_lease(self, request, timeout):
        require(request == self.request and self.inspection_id is not None,
                "unapproved", "Inspection must reserve its record before acquiring a source")
        require(self.maintenance_verifier is not None, "recovery_required", "External administration exclusion is not established")
        deadline = self.clock() + timeout
        lock_id = digest((request.project_id + "/" + request.run_id).encode())
        with self.store.lock("sandbox-" + lock_id + ".lock", blocking=False):
            excluded = self.maintenance_verifier(request, max(0, deadline - self.clock()))
            require(excluded is True and self.clock() < deadline,
                    "recovery_required", "External administration exclusion is not established")
            yield SourceLease(cooperative=True, external_admin_excluded=True)


class EnvironmentCheckpoint:
    """Persist adapter intent/ownership inside the already reserved environment.

    Values are private administration metadata, never exported check evidence.
    Caller must supply this same sink to networking and service adapters.
    """
    def __init__(self, session, run_id, plan):
        self.session, self.run_id = session, run_id
        self.artifact_id, self.plan_sha256 = plan["artifact_id"], digest(canonical(plan))
        hash_value(self.artifact_id)

    def __call__(self, event):
        from .environment import Environment
        require(isinstance(event, dict) and isinstance(event.get("event"), str) and
                event.get("artifact_id") == self.artifact_id and len(canonical(event)) <= 1048576,
                "invalid_input", "Invalid environment ownership checkpoint")
        if "plan_sha256" in event:
            require(event["plan_sha256"] == self.plan_sha256, "changed_input", "Adapter checkpoint plan changed")
        store = self.session.launcher.store
        with store.lock("ledger.lock", blocking=False):
            ledger = store.read()
            _, run, _ = Environment.owned(self.session, ledger, self.run_id)
            record = run.get("environment", {})
            require(record.get("artifact_id") == self.artifact_id and record.get("plan_sha256") == self.plan_sha256 and
                    record.get("state") not in ("planned", "environment-blocked", "environment-check-passed", "environment-check-failed", "environment-held"),
                    "recovery_required", "Environment checkpoint has no active preparation")
            events = record.setdefault("adapter_checkpoints", [])
            require(len(events) < 256 and sum(len(canonical(value)) for value in events) + len(canonical(event)) <= 4194304,
                    "input_limit", "Environment checkpoint budget exhausted")
            events.append(deepcopy(event))
            store.write(ledger)
