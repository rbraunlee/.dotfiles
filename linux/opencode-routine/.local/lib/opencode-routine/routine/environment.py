"""Durable environment plans and gated component lifecycle, never slice admission."""
import os
from pathlib import Path
import time

from .contracts import RoutineError, canonical, digest, identifier, load_package, parse_json, require
from .credentials import CredentialBroker, CredentialFiles
from .launcher import now
from .policy import environment_policy
from .proxy import retained_file, sync_directory


TERMINAL = ("environment-blocked", "environment-check-passed", "environment-check-failed")
DIAGNOSTICS = {"policy_unavailable", "adapter_failed", "command_timeout", "input_limit", "invalid_credential",
               "unsafe_state", "invalid_runtime", "resource_limits_unavailable", "disk_quota_unavailable", "io_error",
               "recovery_required", "credential_cleanup_unconfirmed"}


class DisabledEnvironmentAdapter:
    def preflight(self, plan, timeout):
        # No profile field, Coordinator flag, fake evidence or service health result
        # can override the missing host enforcement/qualification gate.
        raise RoutineError("policy_unavailable", "Environment network, service and credential execution is not approved or qualified")


class Environment:
    def __init__(self, adapter=None, broker=None, clock=time.time):
        self.adapter = adapter or DisabledEnvironmentAdapter()
        self.broker = broker or CredentialBroker()
        self.clock = clock

    @staticmethod
    def owned(session, ledger, run_id):
        require(session.active, "inactive_coordinator", "Coordinator lease has ended")
        launcher = session.launcher
        feature = launcher.feature(ledger, launcher.key(session.project_id, session.feature_id))
        require(feature["coordinator"] and feature["coordinator"]["token"] == session.token,
                "inactive_coordinator", "Coordinator does not own this feature")
        run_key = f"{session.project_id}/{run_id}"
        require(run_key in ledger["runs"], "unapproved", "Run has no exclusive claim")
        run = ledger["runs"][run_key]
        require(run["request"]["feature_id"] == session.feature_id and run["request"]["coordinator_id"] == session.coordinator_id,
                "unapproved", "Run does not belong to this Coordinator/feature")
        return run_key, run, feature

    @staticmethod
    def update(session, run_key, **values):
        store = session.launcher.store
        with store.lock("ledger.lock"):
            ledger = store.read()
            run = ledger["runs"][run_key]
            run["environment"].update(values)
            store.write(ledger)
            return run

    @staticmethod
    def lock_id(session, run_id):
        identifier(run_id)
        require(session.active, "inactive_coordinator", "Coordinator lease has ended")
        return digest(f"{session.project_id}/{run_id}".encode())

    def prepare(self, session, run_id):
        lock_id = self.lock_id(session, run_id)
        store = session.launcher.store
        with store.lock("sandbox-" + lock_id + ".lock", blocking=False):
            with store.lock("ledger.lock"):
                ledger = store.read()
                run_key, run, feature = self.owned(session, ledger, run_id)
                if "environment" in run:
                    require(run["environment"]["state"] == "planned" or run["environment"]["state"] in TERMINAL,
                            "recovery_required", "Interrupted/held environment requires deliberate recovery")
                    return {"run": run, "existing": True}
                require(run["state"] == "claimed" and ("proxy" not in run or run["proxy"]["state"] in ("proxy-check-passed", "proxy-check-failed")),
                        "recovery_required", "Environment planning requires an unused claim without held proxy work")
                package = load_package(Path(feature["project_root"]), session.feature_id)
                require(package == feature["package"], "changed_input", "Approved inputs changed before environment preparation")
                artifact_id = digest(("environment:" + run_key).encode())
                plan = environment_policy(package["profile"], artifact_id)
                plan.update(request=run["request"], baseline=run["baseline"], bundle_sha256=run["bundle_sha256"],
                            profile_sha256=run["profile_sha256"])
                data = canonical(plan)
                reserved = sum(binding["max_bytes"] for binding in plan["credentials"])
                require(len(data) + reserved <= run["resources"]["disk_mb"] * 1048576,
                        "input_limit", "Environment plan/credential staging exceeds preparation budget")
                run.setdefault("preparation_started_at", now())
                run.setdefault("preparation_epoch", self.clock())
                require(run["preparation_epoch"] + run["budgets"]["slice_seconds"] > self.clock(),
                        "command_timeout", "Slice preparation budget exhausted")
                run["environment"] = {"state": "planning", "artifact_id": artifact_id, "started_at": now(),
                                      "plan_sha256": digest(data), "open_gates": plan["open_gates"], "activation_enabled": False}
                store.write(ledger)
            directory = store.root / "artifacts" / artifact_id
            # Planning intent remains durable on error; no implicit retry/adoption
            # of a partially prepared artifact directory.
            directory.parent.mkdir(mode=0o700, exist_ok=True)
            store._private(directory.parent, directory=True)
            directory.mkdir(mode=0o700)
            store._private(directory, directory=True)
            retained_file(directory / "plan.json", data, 0o600)
            sync_directory(directory)
            sync_directory(directory.parent)
            require(run["preparation_epoch"] + run["budgets"]["slice_seconds"] > self.clock(),
                    "command_timeout", "Environment preparation exceeded its deadline")
            run = self.update(session, run_key, state="planned", planned_at=now())
            return {"run": run, "existing": False}

    def launch(self, session, run_id):
        lock_id = self.lock_id(session, run_id)
        store = session.launcher.store
        with store.lock("sandbox-" + lock_id + ".lock", blocking=False):
            with store.lock("ledger.lock"):
                ledger = store.read()
                run_key, run, feature = self.owned(session, ledger, run_id)
                require("environment" in run, "unapproved", "Run has no prepared environment plan")
                record = run["environment"]
                if record["state"] in TERMINAL:
                    return {"run": run, "existing": True}
                require(record["state"] == "planned" and run["state"] == "claimed",
                        "recovery_required", "Interrupted/held environment requires deliberate recovery")
                package = load_package(Path(feature["project_root"]), session.feature_id)
                require(package == feature["package"], "changed_input", "Approved environment inputs changed")
                directory = store.root / "artifacts" / record["artifact_id"]
                store._private(directory.parent, directory=True)
                store._private(directory, directory=True)
                path = directory / "plan.json"
                store._private(path)
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
                with os.fdopen(fd, "rb") as stream:
                    data = stream.read(run["resources"]["disk_mb"] * 1048576 + 1)
                require(digest(data) == record["plan_sha256"], "changed_input", "Retained environment plan changed")
                plan = parse_json(data)
                expected = environment_policy(package["profile"], record["artifact_id"])
                expected.update(request=run["request"], baseline=run["baseline"], bundle_sha256=run["bundle_sha256"],
                                profile_sha256=run["profile_sha256"])
                require(plan == expected, "changed_input", "Environment plan differs from approved inputs")
                deadline = run["preparation_epoch"] + run["budgets"]["slice_seconds"]
                require(deadline > self.clock(), "command_timeout", "Environment runtime budget exhausted")
                record.update(state="preparing", attempted_components=[])
                store.write(ledger)

            def remaining():
                require(deadline > self.clock(), "command_timeout", "Environment runtime budget exhausted")
                return min(deadline - self.clock(), run["resources"]["command_seconds"])

            def invoke(operation, *args, limit=None):
                timeout = remaining() if limit is None else min(remaining(), limit)
                command_deadline = self.clock() + timeout
                result = operation(*args, timeout)
                require(self.clock() < command_deadline, "command_timeout", "Environment command exceeded its deadline")
                remaining()
                return result

            effects, stopped, ready = False, True, False
            attempted = []
            diagnostic = None
            files = CredentialFiles(directory / "credentials", self.broker, clock=self.clock)
            metadata = []
            try:
                if hasattr(self.adapter, "bind_host_interfaces"):
                    from .checkpoints import EnvironmentCheckpoint
                    self.adapter.bind_host_interfaces(EnvironmentCheckpoint(session, run_id, plan),
                                                      lambda current_plan, binding: files.path(binding))
                invoke(self.adapter.preflight, plan)
                self.update(session, run_key, state="creating-networks", effects_attempted=True)
                effects = True
                invoke(self.adapter.create_networks, plan)
                self.update(session, run_key, state="enforcing-policy")
                invoke(self.adapter.enforce_policy, plan)
                self.update(session, run_key, state="staging-credentials")
                service_bindings = [binding for binding in plan["credentials"] if binding["consumer"] in plan["components"]]
                metadata = files.stage(run["request"], service_bindings, checkpoint=remaining,
                                       max_bytes=run["resources"]["disk_mb"] * 1048576 - len(data))
                for component in plan["components"]:
                    remaining()
                    attempted.append(component)
                    self.update(session, run_key, state="starting", attempted_components=list(attempted))
                    stopped = False
                    # Never hand another consumer's credential metadata to a service
                    # or proxy. Provider bindings are reserved for the future worker.
                    bindings = [binding for binding in metadata if binding["consumer"] == component]
                    service = next((service for service in plan["services"] if "service:" + service["id"] == component), None)
                    start_limit = service["resources"]["command_seconds"] if service else None
                    invoke(self.adapter.start_component, plan, component, bindings, limit=start_limit)
                    limit = service["readiness"]["timeout_seconds"] if service else None
                    invoke(self.adapter.wait_ready, plan, component, limit=limit)
                remaining()
                ready = True
                self.update(session, run_key, state="ready")
            except (RoutineError, OSError) as exc:
                diagnostic = (exc.code if isinstance(exc.code, str) and exc.code in DIAGNOSTICS else "adapter_failed") if isinstance(exc, RoutineError) else "io_error"
            finally:
                if attempted:
                    try:
                        self.update(session, run_key, state="stopping")
                    except (RoutineError, OSError):
                        diagnostic = "io_error"
                    try:
                        stop_deadline = self.clock() + 20
                        stopped = self.adapter.stop_components(plan, list(reversed(attempted)), 20) is True and self.clock() < stop_deadline
                    except (RoutineError, OSError):
                        stopped = False
                if stopped:
                    try:
                        files.cleanup()
                    except (RoutineError, OSError):
                        diagnostic = "credential_cleanup_unconfirmed"
            state = "environment-check-passed" if ready and diagnostic is None else "environment-check-failed"
            if diagnostic == "policy_unavailable" and not effects:
                state = "environment-blocked"
            if not stopped or diagnostic == "credential_cleanup_unconfirmed":
                state = "environment-held"
                if not stopped:
                    diagnostic = "stop_unconfirmed"
            evidence = {"version": 1, "request": run["request"], "plan_sha256": record["plan_sha256"],
                        "outcome": state, "diagnostic": diagnostic, "effects_attempted": effects,
                        "attempted_components": attempted, "components_stopped": stopped, "credentials": metadata,
                        "qualified": False, "egress_enabled": False}
            evidence_hash = None
            try:
                retained_file(directory / "evidence.json", canonical(evidence), 0o600)
                sync_directory(directory)
                evidence_hash = digest(canonical(evidence))
            except OSError:
                if state != "environment-held":
                    state, diagnostic = "environment-check-failed", "io_error"
            run = self.update(session, run_key, state=state, completed_at=now(),
                              result={"outcome": state, "diagnostic": diagnostic, "effects_attempted": effects,
                                      "components_stopped": stopped, "qualified": False, "egress_enabled": False,
                                      "evidence_sha256": evidence_hash})
            return {"run": run, "existing": False}
