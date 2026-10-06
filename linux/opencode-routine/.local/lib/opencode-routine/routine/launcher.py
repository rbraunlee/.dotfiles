"""Authorize, lease, claim and status; M2 delegates offline baseline preparation."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import stat
import uuid

from .contracts import RoutineError, canonical, digest, hash_value, identifier, load_package, require
from .store import Store


def now():
    return datetime.now(timezone.utc).isoformat()


class Launcher:
    def __init__(self, store=None, local_adapter=None):
        self.store = store or Store()
        self.local_adapter = local_adapter

    def local_stop(self, project_id, feature_id, run_id):
        """Stopping-only trusted operation; never waits for a lifecycle driver."""
        from .local_lifecycle import request_stop

        return request_stop(self, project_id, feature_id, run_id)

    @staticmethod
    def key(project_id, feature_id):
        return f"{identifier(project_id)}/{identifier(feature_id)}"

    @staticmethod
    def feature(ledger, key):
        require(key in ledger["features"], "unapproved", "Feature has no host authorization")
        return ledger["features"][key]

    def authorize(self, project_id, feature_id, project_root):
        """Trusted user operation; never exposed to a worker or Coordinator tool."""
        identifier(project_id)
        root = Path(project_root).absolute()
        require(root.is_dir() and not any(p.is_symlink() for p in (root, *root.parents)),
                "invalid_path", "Project root must be a real directory without symlink ancestors")
        root = root.resolve()
        require(not self.store.root.is_relative_to(root), "unsafe_state", "Host ledger cannot live inside the project")
        package = load_package(root, feature_id)
        key = self.key(project_id, feature_id)
        # Raw input bytes are included: even formatting drift requires renewed approval.
        authorization_id = digest(canonical({"project_id": project_id, "root": str(root), "package": package}))
        with self.store.lock("ledger.lock"):
            ledger = self.store.read()
            for existing_key, existing in ledger["features"].items():
                if existing_key.split("/")[0] == project_id:
                    require(existing["project_root"] == str(root), "identity_conflict", "Project ID already names another root")
            if key in ledger["features"]:
                feature = ledger["features"][key]
                require(feature["authorization_id"] == authorization_id,
                        "identity_conflict", "Feature ID already has different immutable inputs")
                return {"authorization_id": authorization_id, "feature_id": feature_id, "existing": True}
            ledger["features"][key] = {
                "project_root": str(root), "authorization_id": authorization_id,
                "package": package, "authorized_at": now(), "coordinator": None,
                "slices": {ticket["slice_id"]: {"state": "pending", "run_id": None}
                           for ticket in package["manifest"]["tickets"]},
            }
            self.store.write(ledger)
        return {"authorization_id": authorization_id, "feature_id": feature_id, "existing": False}

    def _local_root(self, project_root):
        root = Path(project_root).absolute()
        require(root.is_dir() and not any(p.is_symlink() for p in (root, *root.parents)),
                "invalid_path", "Project root must be a real directory without linked ancestors")
        root = root.resolve()
        require(not self.store.root.is_relative_to(root), "unsafe_state", "Host state cannot live inside the project")
        return root

    @staticmethod
    def _reviewed_input(path, expected, limit):
        path = Path(path).absolute()
        require(not any(p.is_symlink() for p in (path, *path.parents)),
                "invalid_path", "Reviewed inputs cannot have linked paths")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as stream:
            require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode),
                    "invalid_input", "Reviewed inputs must be regular files")
            data = stream.read(limit + 1)
        require(len(data) <= limit, "input_limit", "Reviewed input exceeds the approved byte limit")
        require(digest(data) == expected, "changed_input", "Reviewed input identity differs from the profile")

    def _check_local_inputs(self, feature, baseline=None):
        from .local_baseline import inspect_baseline
        from .local_bundle import verify_snapshot
        from .local_contracts import load_package as load_local_package

        current = load_local_package(Path(feature["project_root"]), feature["package"]["manifest"]["feature_id"])
        require(current == feature["package"], "changed_input", "Planning inputs changed since local authorization")
        limits = current["profile"]["command_limits"]
        verify_snapshot(Path(feature["bundle_snapshot"]["path"]), current["manifest"]["bundle_sha256"],
                        max_bytes=limits["input_bytes"], timeout=limits["command_seconds"])
        inspect_baseline(feature["project_root"], baseline or feature["verified_head"],
                         timeout=limits["command_seconds"], max_bytes=limits["output_bytes"],
                         temporary_root=self.store.root)
        return current

    def authorize_local(self, project_id, feature_id, project_root, bundle_root,
                        api_path, configuration_path, fixture_evidence):
        """Trusted fixture administration; no checkout, project commands or sessions."""
        from .local_baseline import inspect_baseline
        from .local_bundle import describe_bundle, snapshot_bundle, verify_snapshot
        from .local_contracts import load_package as load_local_package, validate_fixture_evidence

        key = self.key(project_id, feature_id)
        root = self._local_root(project_root)
        package = load_local_package(root, feature_id)
        validate_fixture_evidence(fixture_evidence, package)
        fixture_evidence = deepcopy(fixture_evidence)
        limits = package["profile"]["command_limits"]
        runtime = package["profile"]["runtime"]
        self._reviewed_input(api_path, runtime["api_sha256"], limits["input_bytes"])
        self._reviewed_input(configuration_path, runtime["configuration_sha256"], limits["input_bytes"])
        described = describe_bundle(bundle_root, max_bytes=limits["input_bytes"], timeout=limits["command_seconds"])
        require(described["sha256"] == package["manifest"]["bundle_sha256"],
                "changed_input", "Local bundle differs from the approved inventory")
        authorization_id = digest(canonical({"project_id": project_id, "root": str(root),
                                             "execution": "trusted-local", "schema_version": 1,
                                             "package": package, "fixture_evidence": fixture_evidence}))
        # Serialize feature snapshot publication, not expensive work under ledger.lock.
        with self.store.lock("local-authorization-" + digest(key.encode()) + ".lock"):
            with self.store.lock("ledger.lock"):
                ledger = self.store.read()
                self._check_project_identity(ledger, project_id, root)
                existing = ledger["features"].get(key)
                if existing is not None:
                    require(existing.get("execution") == "trusted-local", "execution_mismatch",
                            "Historical features cannot acquire local execution authority")
                    require(existing["authorization_id"] == authorization_id, "identity_conflict",
                            "Feature ID already has different immutable inputs")
                    existing = deepcopy(existing)
            if existing is not None:
                self._check_local_inputs(existing)
                return {"authorization_id": authorization_id, "feature_id": feature_id, "existing": True}
            baseline = package["manifest"]["baseline"]
            inspect_baseline(root, baseline, timeout=limits["command_seconds"], max_bytes=limits["output_bytes"],
                             temporary_root=self.store.root)
            artifacts = self.store.root / "artifacts"
            require(not artifacts.is_symlink(), "unsafe_state", "Linked artifact storage is forbidden")
            artifacts.mkdir(mode=0o700, exist_ok=True)
            self.store._private(artifacts, directory=True)
            destination = artifacts / ("local-bundle-" + authorization_id)
            copied = snapshot_bundle(bundle_root, destination, described["sha256"],
                                     max_bytes=limits["input_bytes"], timeout=limits["command_seconds"])
            require(copied == described, "changed_input", "Bundle inventory changed during authorization")
            verify_snapshot(destination, described["sha256"], max_bytes=limits["input_bytes"],
                            timeout=limits["command_seconds"])
            require(load_local_package(root, feature_id) == package, "changed_input",
                    "Planning inputs changed during local authorization")
            self._reviewed_input(api_path, runtime["api_sha256"], limits["input_bytes"])
            self._reviewed_input(configuration_path, runtime["configuration_sha256"], limits["input_bytes"])
            inspect_baseline(root, baseline, timeout=limits["command_seconds"], max_bytes=limits["output_bytes"],
                             temporary_root=self.store.root)
            with self.store.lock("ledger.lock"):
                ledger = self.store.read()
                self._check_project_identity(ledger, project_id, root)
                require(key not in ledger["features"], "identity_conflict", "Feature was authorized concurrently")
                ledger["features"][key] = {
                    "schema_version": 1, "execution": "trusted-local", "project_root": str(root),
                    "authorization_id": authorization_id, "package": package, "authorized_at": now(),
                    "fixture_evidence": fixture_evidence, "verified_head": dict(baseline),
                    "bundle_snapshot": {"path": str(destination), **copied}, "coordinator": None,
                    "dispatches": {}, "slices": {ticket["slice_id"]: {"state": "pending", "run_id": None}
                                                for ticket in package["manifest"]["tickets"]},
                }
                self.store.write(ledger)
        return {"authorization_id": authorization_id, "feature_id": feature_id, "existing": False}

    @staticmethod
    def _check_project_identity(ledger, project_id, root):
        for existing_key, existing in ledger["features"].items():
            if existing_key.split("/")[0] == project_id:
                require(existing["project_root"] == str(root), "identity_conflict", "Project ID already names another root")

    def authorize_local_dispatch(self, project_id, feature_id, slice_id, dispatch_id, authorization_id):
        key = self.key(project_id, feature_id)
        identifier(slice_id)
        identifier(dispatch_id)
        hash_value(authorization_id)
        with self.store.lock("ledger.lock"):
            ledger = self.store.read()
            feature = deepcopy(self.feature(ledger, key))
            require(feature.get("execution") == "trusted-local", "execution_mismatch", "Dispatch requires a local feature")
            require(feature["authorization_id"] == authorization_id, "unapproved", "Authorization identity mismatch")
            require(slice_id in feature["slices"], "unapproved", "Slice is outside the approved graph")
        self._check_local_inputs(feature)
        request = {"schema_version": 1, "execution": "trusted-local", "project_id": project_id,
                   "feature_id": feature_id, "slice_id": slice_id, "dispatch_id": dispatch_id,
                   "authorization_id": authorization_id, "baseline": feature["verified_head"]}
        dispatch_authorization_id = digest(canonical(request))
        with self.store.lock("ledger.lock"):
            ledger = self.store.read()
            current = self.feature(ledger, key)
            require(current["authorization_id"] == authorization_id and current["verified_head"] == request["baseline"],
                    "changed_input", "Feature authorization or verified head changed during dispatch authorization")
            dispatches = current["dispatches"]
            existing = dispatch_id in dispatches
            if existing:
                require(dispatches[dispatch_id]["request"] == request, "identity_conflict",
                        "Dispatch ID reused with different scope or baseline")
            else:
                dispatches[dispatch_id] = {"request": request, "dispatch_authorization_id": dispatch_authorization_id,
                                           "authorized_at": now()}
                self.store.write(ledger)
        return {"dispatch_id": dispatch_id, "dispatch_authorization_id": dispatch_authorization_id, "existing": existing}

    @contextmanager
    def coordinator(self, project_id, feature_id, coordinator_id):
        key = self.key(project_id, feature_id)
        identifier(coordinator_id)
        lock_name = "coordinator-" + digest(key.encode()) + ".lock"
        # OS lease, not an expiring Markdown flag. A crashed owner releases the lock.
        with self.store.lock(lock_name, blocking=False):
            token = uuid.uuid4().hex
            with self.store.lock("ledger.lock"):
                ledger = self.store.read()
                feature = self.feature(ledger, key)
                previous = feature["coordinator"]
                require(previous is None, "recovery_required",
                        "Previous Coordinator did not close cleanly; deliberate recovery is not implemented until M5")
                feature["coordinator"] = {"id": coordinator_id, "token": token, "opened_at": now()}
                self.store.write(ledger)
            session = Coordinator(self, project_id, feature_id, coordinator_id, token)
            try:
                yield session
            finally:
                session.active = False
                with self.store.lock("ledger.lock"):
                    ledger = self.store.read()
                    feature = self.feature(ledger, key)
                    if feature["coordinator"] and feature["coordinator"]["token"] == token:
                        feature["coordinator"] = None
                        self.store.write(ledger)

    def status(self, project_id, feature_id):
        key = self.key(project_id, feature_id)
        with self.store.lock("ledger.lock"):
            ledger = self.store.read()
            feature = self.feature(ledger, key)
        # An observational view of one ledger revision; status never updates state
        # or adopts a changed ref. Hashing/Git work is outside ledger.lock.
        manifest = feature["package"]["manifest"]
        local = feature.get("execution") == "trusted-local"
        hold_reasons = []
        if local:
            try:
                self._check_local_inputs(feature)
            except RoutineError as exc:
                hold_reasons.append(exc.code)
            except OSError:
                hold_reasons.append("io_error")
        if local and feature["coordinator"]:
            try:
                with self.store.lock("coordinator-" + digest(key.encode()) + ".lock", blocking=False):
                    hold_reasons.append("coordinator_recovery_required")
            except RoutineError as exc:
                if exc.code != "coordinator_busy":
                    raise
        slices = {}
        for ticket in manifest["tickets"]:
            entry = dict(feature["slices"][ticket["slice_id"]])
            entry["waiting_for"] = [dep for dep in ticket["dependencies"]
                                    if feature["slices"][dep]["state"] != "integrated"]
            entry["eligible"] = entry["state"] == "pending" and not entry["waiting_for"]
            if local:
                entry["dispatch_ids"] = [dispatch_id for dispatch_id, dispatch in feature["dispatches"].items()
                                         if dispatch["request"]["slice_id"] == ticket["slice_id"] and
                                         dispatch["request"]["baseline"] == feature["verified_head"]]
                entry["hold_reasons"] = list(hold_reasons)
                if not entry["dispatch_ids"]:
                    entry["hold_reasons"].append("dispatch_not_authorized")
                entry["eligible"] = entry["eligible"] and not entry["hold_reasons"]
            if entry["run_id"]:
                run = ledger["runs"][f"{project_id}/{entry['run_id']}"]
                entry["result"] = run.get("result")
                if local:
                    entry["execution"] = run["execution"]
                    entry["baseline"] = run["baseline"]
                    entry["local"] = run.get("local")
                    if run["state"] == "local-held":
                        entry["hold_reasons"].append("local_recovery_required")
                    lifecycle = run.get("local", {})
                    if lifecycle.get("driver"):
                        # Observation only: no takeover, budget reset or state write.
                        try:
                            name = "local-lifecycle-" + digest(f"{project_id}/{entry['run_id']}".encode()) + ".lock"
                            with self.store.lock(name, blocking=False):
                                entry["hold_reasons"].append("local_driver_missing")
                        except RoutineError as exc:
                            if exc.code != "coordinator_busy":
                                raise
                    stop_request = lifecycle.get("stop_request")
                    if stop_request:
                        entry["hold_reasons"].append("local_stop_requested")
                        import time

                        if time.time() > stop_request["requested_at"] + run["command_limits"]["command_seconds"]:
                            entry["hold_reasons"].append("local_stop_unconfirmed")
                if "proxy" in run:
                    entry["proxy"] = run["proxy"]
                if "environment" in run:
                    entry["environment"] = run["environment"]
            slices[ticket["slice_id"]] = entry
        result = {"project_id": project_id, "feature_id": feature_id,
                  "authorization_id": feature["authorization_id"],
                  "coordinator": feature["coordinator"]["id"] if feature["coordinator"] else None,
                  "slices": slices}
        if local:
            result.update(execution="trusted-local", schema_version=1, verified_head=feature["verified_head"],
                          dispatches=feature["dispatches"], hold_reasons=hold_reasons)
        return result


class Coordinator:
    def __init__(self, launcher, project_id, feature_id, coordinator_id, token):
        self.launcher = launcher
        self.project_id = project_id
        self.feature_id = feature_id
        self.coordinator_id = coordinator_id
        self.token = token
        self.active = True

    def local_prepare(self, run_id):
        from .local_lifecycle import LocalLifecycle

        return LocalLifecycle(self.launcher.local_adapter).prepare(self, run_id)

    def local_fixture_check(self, run_id):
        from .local_lifecycle import LocalLifecycle

        return LocalLifecycle(self.launcher.local_adapter).fixture_check(self, run_id)

    def local_stop(self, run_id):
        from .local_lifecycle import owned_run

        with self.launcher.store.lock("ledger.lock"):
            owned_run(self.launcher, self.launcher.store.read(), self.project_id,
                      self.feature_id, run_id, self)
        return self.launcher.local_stop(self.project_id, self.feature_id, run_id)

    def baseline(self, run_id):
        self._require_sandbox(run_id)
        from .sandbox import Sandbox

        return Sandbox().launch(self, run_id)

    def proxy_check(self, run_id):
        self._require_sandbox(run_id)
        from .proxy import ProxyCheck

        return ProxyCheck().launch(self, run_id)

    def environment_plan(self, run_id):
        self._require_sandbox(run_id)
        from .environment import Environment

        return Environment().prepare(self, run_id)

    def environment_check(self, run_id):
        self._require_sandbox(run_id)
        from .environment import Environment

        return Environment().launch(self, run_id)

    def _require_sandbox(self, run_id):
        identifier(run_id)
        with self.launcher.store.lock("ledger.lock"):
            ledger = self.launcher.store.read()
            feature = self.launcher.feature(ledger, self.launcher.key(self.project_id, self.feature_id))
            run = ledger["runs"].get(f"{self.project_id}/{run_id}", {})
            require(feature.get("execution") != "trusted-local" and run.get("execution") != "trusted-local",
                    "execution_mismatch", "Sandbox operations cannot adopt local features or runs")

    def claim_local(self, slice_id, run_id, authorization_id, dispatch_id, baseline):
        from .local_baseline import validate_baseline

        identifier(slice_id)
        identifier(run_id)
        identifier(dispatch_id)
        hash_value(authorization_id)
        validate_baseline(baseline)
        baseline = dict(baseline)
        require(self.active, "inactive_coordinator", "Coordinator lease has ended")
        launcher = self.launcher
        key = launcher.key(self.project_id, self.feature_id)
        with launcher.store.lock("ledger.lock"):
            ledger = launcher.store.read()
            feature = deepcopy(launcher.feature(ledger, key))
            self._local_claim_scope(feature, slice_id, authorization_id, dispatch_id, baseline)
        launcher._check_local_inputs(feature, baseline)
        dispatch = feature["dispatches"][dispatch_id]
        request = {"execution": "trusted-local", "project_id": self.project_id, "feature_id": self.feature_id,
                   "slice_id": slice_id, "run_id": run_id, "authorization_id": authorization_id,
                   "coordinator_id": self.coordinator_id, "dispatch_id": dispatch_id,
                   "dispatch_authorization_id": dispatch["dispatch_authorization_id"], "baseline": baseline}
        with launcher.store.lock("ledger.lock"):
            ledger = launcher.store.read()
            current = launcher.feature(ledger, key)
            self._local_claim_scope(current, slice_id, authorization_id, dispatch_id, baseline)
            require(current["package"] == feature["package"] and current["dispatches"][dispatch_id] == dispatch,
                    "changed_input", "Local authorization changed during claim validation")
            run_key = f"{self.project_id}/{run_id}"
            if run_key in ledger["runs"]:
                run = ledger["runs"][run_key]
                require(run.get("execution") == "trusted-local", "execution_mismatch", "Historical run IDs cannot become local runs")
                require(run["request"] == request, "identity_conflict", "Run ID reused with different inputs")
                return {"run": run, "existing": True}
            ticket = next(t for t in current["package"]["manifest"]["tickets"] if t["slice_id"] == slice_id)
            waiting = [dep for dep in ticket["dependencies"] if current["slices"][dep]["state"] != "integrated"]
            require(not waiting, "dependencies_unsatisfied", "Awaiting verified integration: " + ", ".join(waiting))
            require(current["slices"][slice_id]["state"] == "pending", "slice_claimed", "Slice already has an exclusive claim")
            profile, manifest = current["package"]["profile"], current["package"]["manifest"]
            run = {"schema_version": 1, "execution": "trusted-local", "request": request,
                   "state": "claimed", "claimed_at": now(), "baseline": baseline,
                   "bundle_snapshot": deepcopy(current["bundle_snapshot"]), "bundle_sha256": manifest["bundle_sha256"],
                   "profile_sha256": manifest["profile_sha256"], "spec_sha256": manifest["spec"]["sha256"],
                   "ticket_sha256": ticket["sha256"], "criteria": ticket["criteria"], "budgets": profile["budgets"],
                   "command_limits": profile["command_limits"], "credential_refs": profile["credential_refs"]}
            ledger["runs"][run_key] = run
            current["slices"][slice_id] = {"state": "claimed", "run_id": run_id}
            launcher.store.write(ledger)
            return {"run": run, "existing": False}

    def _local_claim_scope(self, feature, slice_id, authorization_id, dispatch_id, baseline):
        require(feature.get("execution") == "trusted-local", "execution_mismatch", "Local claims require local authorization")
        require(feature["coordinator"] and feature["coordinator"]["token"] == self.token and self.active,
                "inactive_coordinator", "Coordinator does not own this feature")
        require(feature["authorization_id"] == authorization_id, "unapproved", "Authorization identity mismatch")
        dispatch = feature["dispatches"].get(dispatch_id)
        require(dispatch is not None, "unapproved", "No trusted single-slice dispatch authorization")
        require(dispatch["request"]["slice_id"] == slice_id, "unapproved", "Selected slice is outside dispatch scope")
        require(feature["verified_head"] == baseline and dispatch["request"]["baseline"] == baseline,
                "baseline_moved", "Claim baseline differs from the authorized verified head")

    def claim(self, slice_id, run_id, authorization_id):
        identifier(slice_id)
        identifier(run_id)
        hash_value(authorization_id)
        require(self.active, "inactive_coordinator", "Coordinator lease has ended")
        launcher = self.launcher
        key = launcher.key(self.project_id, self.feature_id)
        request = {"project_id": self.project_id, "feature_id": self.feature_id,
                   "slice_id": slice_id, "run_id": run_id, "authorization_id": authorization_id,
                   "coordinator_id": self.coordinator_id}
        with launcher.store.lock("ledger.lock"):
            ledger = launcher.store.read()
            feature = launcher.feature(ledger, key)
            require(feature.get("execution") != "trusted-local", "execution_mismatch", "Historical claims cannot adopt a local feature")
            require(feature["coordinator"] and feature["coordinator"]["token"] == self.token,
                    "inactive_coordinator", "Coordinator does not own this feature")
            require(feature["authorization_id"] == authorization_id, "unapproved", "Authorization identity mismatch")
            current = load_package(Path(feature["project_root"]), self.feature_id)
            require(current == feature["package"], "changed_input", "Planning inputs changed since authorization")
            require(slice_id in feature["slices"], "unapproved", "Slice is not in the approved graph")
            run_key = f"{self.project_id}/{run_id}"
            if run_key in ledger["runs"]:
                run = ledger["runs"][run_key]
                require(run.get("execution") != "trusted-local", "execution_mismatch", "Historical claims cannot adopt local run IDs")
                require(run["request"] == request, "identity_conflict", "Run ID reused with different inputs")
                return {"run": run, "existing": True}
            ticket = next(t for t in current["manifest"]["tickets"] if t["slice_id"] == slice_id)
            waiting_for = [dep for dep in ticket["dependencies"] if feature["slices"][dep]["state"] != "integrated"]
            require(not waiting_for, "dependencies_unsatisfied", "Awaiting verified integration: " + ", ".join(waiting_for))
            require(feature["slices"][slice_id]["state"] == "pending", "slice_claimed", "Slice already has an exclusive claim")
            run = {"request": request, "state": "claimed", "claimed_at": now(),
                   "baseline": current["manifest"]["baseline"], "bundle_sha256": current["manifest"]["bundle_sha256"],
                   "profile_sha256": current["manifest"]["profile_sha256"],
                   "spec_sha256": current["manifest"]["spec"]["sha256"], "ticket_sha256": ticket["sha256"],
                   "criteria": ticket["criteria"], "resources": current["profile"]["resources"],
                   "budgets": current["profile"]["budgets"], "credential_refs": current["profile"]["credential_refs"]}
            ledger["runs"][run_key] = run
            feature["slices"][slice_id] = {"state": "claimed", "run_id": run_id}
            launcher.store.write(ledger)
            return {"run": run, "existing": False}
