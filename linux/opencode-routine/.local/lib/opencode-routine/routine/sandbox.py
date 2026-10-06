"""Claim -> offline baseline -> bounded evidence -> retained stopped container."""
from pathlib import Path
import time

from .compose import DockerCompose, compose_document, offline_profile
from .contracts import RoutineError, canonical, digest, fields, hash_value, identifier, load_package, require
from .launcher import now
from .inputs import stage_mounts
from .transfer import export_bundle


DIAGNOSTICS = {"bootstrap_failed", "input_identity_mismatch", "unsafe_clone", "service_start_failed",
                "service_identity_mismatch", "api_failed", "api_output_limit", "runtime_timeout",
                "required_command_failed", "service_auth_unavailable", "input_snapshot_mismatch", "command_timeout"}


def validate_evidence(evidence, run, package, input_bundle_sha256):
    """Admission here is baseline evidence only, never product merge authority."""
    require(isinstance(evidence, dict) and type(evidence.get("version")) is int and evidence["version"] in (1, 2),
            "invalid_evidence", "Unsupported evidence version")
    fields(evidence, ("version", "request", "baseline", "bundle_sha256", "profile_sha256", "input_bundle_sha256",
                      "outcome", "service", "checks", "diagnostic") + (("mounts",) if evidence["version"] == 2 else ()), "baseline evidence")
    expected_mounts = package.get("mounts", [])
    observed_mounts = evidence.get("mounts", [])
    require(isinstance(observed_mounts, list) and len(observed_mounts) <= len(expected_mounts),
            "invalid_evidence", "Unexpected input snapshot evidence")
    for observed, expected_mount in zip(observed_mounts, expected_mounts):
        fields(observed, ("source", "target", "sha256", "size_bytes"), "input snapshot evidence")
        require(type(observed["size_bytes"]) is int and observed == expected_mount,
                "invalid_evidence", "Input snapshot evidence does not match the approved file")
    for key in ("request", "baseline", "bundle_sha256", "profile_sha256"):
        require(evidence[key] == run[key], "invalid_evidence", "Evidence does not identify the claimed inputs")
    require(evidence["input_bundle_sha256"] == input_bundle_sha256, "invalid_evidence", "Git bundle evidence identity mismatch")
    require(evidence["outcome"] in ("passed", "failed"), "invalid_evidence", "Unknown baseline outcome")
    require(evidence["diagnostic"] is None or
            (isinstance(evidence["diagnostic"], str) and evidence["diagnostic"] in DIAGNOSTICS),
            "invalid_evidence", "Unknown diagnostic; raw messages are forbidden")
    if evidence["service"] is not None:
        service = evidence["service"]
        fields(service, ("version", "pid", "hostname", "uid", "location"), "service evidence")
        require(service["version"] == package["profile"]["runtime"]["opencode_version"] and
                type(service["pid"]) is int and service["pid"] > 0 and service["uid"] == 10001 and
                service["location"] == "/control", "invalid_evidence", "Unapproved service identity/location")
        identifier(service["hostname"])
    require(isinstance(evidence["checks"], list), "invalid_evidence", "Expected command evidence list")
    require((evidence["service"] is None and not evidence["checks"]) or observed_mounts == expected_mounts,
            "invalid_evidence", "Commands or a service cannot precede input snapshot verification")
    commands = package["profile"]["commands"]
    expected = [(f"setup-{index:02d}", "setup", entry) for index, entry in enumerate(commands["setup"], 1)]
    expected += [(name, "check", entry) for name, entry in commands["checks"].items()]
    require(len(evidence["checks"]) <= len(expected), "invalid_evidence", "Unexpected command evidence")
    for check, (name, stage, entry) in zip(evidence["checks"], expected):
        fields(check, ("id", "stage", "argv_sha256", "shell_id", "status", "exit", "output_sha256", "output_truncated"), "command evidence")
        require(check["id"] == name and check["stage"] == stage and check["argv_sha256"] == digest(canonical(entry["argv"])),
                "invalid_evidence", "Command evidence does not match approved order/arguments")
        require(isinstance(check["shell_id"], str) and check["shell_id"].startswith("sh_") and
                len(check["shell_id"]) <= 128 and check["status"] in ("exited", "timeout", "killed") and
                (check["exit"] is None or type(check["exit"]) is int) and type(check["output_truncated"]) is bool,
                "invalid_evidence", "Malformed command outcome")
        hash_value(check["output_sha256"])
    if evidence["outcome"] == "passed":
        require(evidence["service"] is not None and evidence["diagnostic"] is None and
                observed_mounts == expected_mounts and
                len(evidence["checks"]) == len(expected) and
                all(check["status"] == "exited" and check["exit"] == 0 for check in evidence["checks"]),
                "invalid_evidence", "Missing or failed required commands cannot establish a baseline pass")
    else:
        require(evidence["diagnostic"] is not None, "invalid_evidence", "Failed baseline requires a diagnostic code")
    return evidence


class Sandbox:
    def __init__(self, adapter=None, export=export_bundle, clock=time.time):
        self.adapter = adapter or DockerCompose()
        self.export = export
        self.clock = clock

    def launch(self, session, run_id):
        identifier(run_id)
        require(session.active, "inactive_coordinator", "Coordinator lease has ended")
        launcher = session.launcher
        store = launcher.store
        key = launcher.key(session.project_id, session.feature_id)
        run_key = f"{session.project_id}/{run_id}"
        artifact_id = digest(run_key.encode())
        with store.lock("sandbox-" + artifact_id + ".lock", blocking=False):
            with store.lock("ledger.lock"):
                ledger = store.read()
                feature = launcher.feature(ledger, key)
                require(feature["coordinator"] and feature["coordinator"]["token"] == session.token,
                        "inactive_coordinator", "Coordinator does not own this feature")
                require(run_key in ledger["runs"], "unapproved", "Run has no exclusive claim")
                run = ledger["runs"][run_key]
                require(run["request"]["feature_id"] == session.feature_id and
                        run["request"]["coordinator_id"] == session.coordinator_id,
                        "unapproved", "Run does not belong to this Coordinator/feature")
                require("proxy" not in run or run["proxy"]["state"] in ("proxy-check-passed", "proxy-check-failed"),
                        "recovery_required", "Interrupted/held proxy requires deliberate recovery before a baseline")
                require("environment" not in run or run["environment"]["state"] in
                        ("planned", "environment-blocked", "environment-check-passed", "environment-check-failed"),
                        "recovery_required", "Interrupted/held environment requires deliberate recovery before a baseline")
                if run["state"] in ("baseline-passed", "sandbox-failed"):
                    return {"run": run, "existing": True}
                require(run["state"] == "claimed", "recovery_required", "Sandbox already started; implicit relaunch is forbidden")
                package = load_package(Path(feature["project_root"]), session.feature_id)
                require(package == feature["package"], "changed_input", "Approved inputs changed before preparation")
                offline_profile(package["profile"])
                run.setdefault("preparation_started_at", now())
                run.setdefault("preparation_epoch", self.clock())
                run.update(state="preparing", artifact_id=artifact_id,
                           runtime_image=package["profile"]["runtime"]["image"],
                           opencode_version=package["profile"]["runtime"]["opencode_version"])
                feature["slices"][run["request"]["slice_id"]]["state"] = "preparing"
                store.write(ledger)
                project_root = feature["project_root"]
            deadline = run["preparation_epoch"] + run["budgets"]["slice_seconds"]

            def remaining():
                require(deadline > self.clock(), "command_timeout", "Sandbox preparation/runtime budget exhausted")
                return deadline - self.clock()

            artifacts = store.root / "artifacts"
            artifacts.mkdir(mode=0o700, exist_ok=True)
            store._private(artifacts, directory=True)
            directory = artifacts / artifact_id
            directory.mkdir(mode=0o700)
            handoff = directory / "handoff"
            handoff.mkdir(mode=0o755)
            started = False
            evidence = None
            diagnostic = None
            stopped = True
            try:
                profile = package["profile"]
                self.adapter.preflight(profile, run["bundle_sha256"], min(30, remaining()))
                preparation_limit = profile["resources"]["disk_mb"] * 1024 * 1024
                mounts = stage_mounts(project_root, profile["mounts"], package.get("mounts", []), handoff,
                                      preparation_limit, checkpoint=remaining)
                context = {"request": run["request"], "baseline": run["baseline"], "bundle_sha256": run["bundle_sha256"],
                           "profile_sha256": run["profile_sha256"], "profile": profile,
                           "criteria": run["criteria"], "planning": package["snapshots"],
                           "mounts": mounts, "input_bundle_sha256": "0" * 64, "deadline_epoch": deadline}
                bundle_limit = preparation_limit - len(canonical(context)) - sum(mount["size_bytes"] for mount in mounts)
                require(bundle_limit > 0, "input_limit", "Planning and input snapshots leave no room for the Git bundle")
                input_hash = self.export(project_root, run["baseline"]["commit"], handoff / "repository.bundle",
                                         timeout=min(profile["resources"]["command_seconds"], remaining()), max_bytes=bundle_limit)
                context["input_bundle_sha256"] = input_hash
                context_bytes = canonical(context)
                require((handoff / "repository.bundle").stat().st_size <= bundle_limit,
                        "input_limit", "Combined handoff exceeds the approved preparation budget")
                (handoff / "context.json").write_bytes(context_bytes)
                for path in handoff.iterdir():
                    path.chmod(0o555 if path.is_dir() else 0o444)
                handoff.chmod(0o555)
                document = compose_document(profile, handoff, artifact_id)
                compose_path = directory / "compose.json"
                compose_path.write_bytes(canonical(document))
                compose_path.chmod(0o600)
                # Record intent before the external creation boundary, including ambiguous failures.
                self.update(session, run_key, state="starting", input_bundle_sha256=input_hash, mounts=mounts,
                            launch_id=document["services"]["worker"]["labels"]["routine.launch-id"])
                started = True
                stopped = False
                container_id = self.adapter.start(directory, artifact_id, min(60, remaining()))
                hash_value(container_id)
                self.update(session, run_key, state="running", container_id=container_id)
                exit_code = self.adapter.wait(artifact_id, remaining())
                evidence = self.adapter.collect(artifact_id, 1024 * 1024, min(30, remaining()))
                validate_evidence(evidence, run, package, input_hash)
                require((exit_code == 0) == (evidence["outcome"] == "passed"),
                        "invalid_evidence", "Container exit disagrees with its reported baseline outcome")
                (directory / "evidence.json").write_bytes(canonical(evidence))
                (directory / "evidence.json").chmod(0o600)
            except (RoutineError, OSError) as exc:
                diagnostic = exc.code if isinstance(exc, RoutineError) else "io_error"
                evidence = None
            finally:
                if started:
                    try:
                        self.adapter.stop(directory, artifact_id)
                        stopped = True
                    except (RoutineError, OSError):
                        stopped = False
            state = "baseline-passed" if evidence and evidence["outcome"] == "passed" else "sandbox-failed"
            if not stopped:
                state, diagnostic = "sandbox-held", "stop_unconfirmed"
            run = self.update(session, run_key, state=state, completed_at=now(),
                              result={"outcome": state, "diagnostic": diagnostic or (evidence["diagnostic"] if evidence else "setup_failed"),
                                      "evidence_sha256": digest(canonical(evidence)) if evidence else None,
                                      "artifact_id": artifact_id, "container_stopped": stopped})
            return {"run": run, "existing": False}

    @staticmethod
    def update(session, run_key, **values):
        store = session.launcher.store
        with store.lock("ledger.lock"):
            ledger = store.read()
            run = ledger["runs"][run_key]
            run.update(values)
            feature = ledger["features"][session.launcher.key(session.project_id, session.feature_id)]
            feature["slices"][run["request"]["slice_id"]]["state"] = run["state"]
            store.write(ledger)
            return run
