"""Trusted administration plus a narrow, process-leased JSON-lines interface."""
import argparse
import json
from pathlib import Path
import sys

from .contracts import RoutineError, fields, parse_json, read_input, require
from .launcher import Launcher


def emit(value):
    print(json.dumps(value, sort_keys=True, allow_nan=False), flush=True)


def error(exc):
    # Never return raw file contents or exception strings from repository inputs.
    if isinstance(exc, RoutineError):
        messages = {
            "invalid_json": "Invalid JSON; duplicate keys and non-finite values are forbidden",
            "invalid_input": "Request or approved input has an invalid shape or value",
            "invalid_id": "Identifier must use 1–64 letters, numbers, underscores or hyphens",
            "invalid_profile": "Approved profile is invalid or unsupported for this operation",
            "invalid_graph": "Approved slice graph is invalid",
            "invalid_path": "Input path is invalid, linked or inaccessible",
            "missing_input": "A required approved input is missing",
            "unresolved_criteria": "Required criterion references do not resolve",
            "unapproved": "Operation is outside the recorded authorization",
            "changed_input": "Approved input identity changed; execution is held",
            "identity_conflict": "An identity was reused with different immutable inputs",
            "execution_mismatch": "Local and historical sandbox identities cannot cross execution paths",
            "baseline_missing": "Verified feature reference or commit is unavailable",
            "baseline_moved": "Feature reference differs from the recorded verified head",
            "invalid_baseline": "Verified baseline object must itself be a commit",
            "unsafe_git": "Git metadata is linked, shared, invalid or changed during inspection",
            "unsupported_checkout": "An ordinary independent Git checkout is required",
            "unsafe_state": "Host state paths, permissions or ownership are unsafe",
            "dependencies_unsatisfied": "Selected slice awaits verified dependency integration; inspect status",
            "slice_claimed": "Selected slice already has an exclusive claim",
            "coordinator_busy": "Another Coordinator holds the feature lease",
            "inactive_coordinator": "Coordinator no longer owns the feature lease",
            "recovery_required": "Interrupted or uncertain work requires deliberate recovery",
            "artifact_exists": "Retained artifact destination exists and cannot be adopted",
            "command_timeout": "Bounded host operation exceeded its deadline",
            "input_limit": "Approved input byte bound was exceeded",
            "output_limit": "Approved output or metadata bound was exceeded",
            "unsupported_operation": "Operation is not available through the typed Coordinator interface",
            "capacity_wait": "Local driver capacity is unavailable; preparation has not started",
            "configuration_unverified": "Effective local configuration is unverified; execution is held",
            "ownership_uncertain": "Owned session, command or descendant identity is uncertain",
            "stop_uncertain": "Owned stopping is unconfirmed; retained work requires recovery",
            "stop_requested": "Owned stopping was requested; execution is held",
        }
        return {"error": {"code": exc.code, "message": messages.get(exc.code, "Operation failed; no success was recorded")}}
    return {"error": {"code": "io_error", "message": "Host I/O failed; no success was recorded"}}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Host routine: explicit local preparation and historical sandbox operations")
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("bundle-id", help="Print the local M2 worker asset fingerprint; does not build an image")
    authorize = commands.add_parser("authorize", help="Trusted user authorization, not a Coordinator operation")
    authorize.add_argument("--project", required=True)
    authorize.add_argument("--feature", required=True)
    authorize.add_argument("--root", required=True)
    local_bundle = commands.add_parser("local-bundle-id", help="Fingerprint selected local agent/skill files; no runtime launch")
    local_bundle.add_argument("--root", required=True)
    local_authorize = commands.add_parser("authorize-local", help="Trusted W1 fixture authorization; no checkout or sessions")
    for name in ("project", "feature", "root", "bundle-root", "api-input", "configuration-input", "fixture-evidence"):
        local_authorize.add_argument("--" + name, required=True)
    dispatch = commands.add_parser("authorize-local-dispatch", help="Trusted single-slice dispatch scope")
    for name in ("project", "feature", "slice", "dispatch", "authorization"):
        dispatch.add_argument("--" + name, required=True)
    status = commands.add_parser("status")
    stop = commands.add_parser("local-stop", help="Request owned stopping without waiting for the lifecycle lock")
    for name in ("project", "feature", "run"):
        stop.add_argument("--" + name, required=True)
    coordinate = commands.add_parser("coordinate", help="Hold an exclusive Coordinator lease until stdin EOF")
    for command in (status, coordinate):
        command.add_argument("--project", required=True)
        command.add_argument("--feature", required=True)
    coordinate.add_argument("--coordinator", required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == "bundle-id":
            from .compose import bundle_identity

            emit({"bundle_sha256": bundle_identity(), "opencode_version": "2.0.22"})
            return 0
        if args.operation == "local-bundle-id":
            from .local_bundle import describe_bundle

            result = describe_bundle(args.root, max_bytes=16 * 1024 * 1024, timeout=60)
            emit({"bundle_sha256": result["sha256"], "inventory": result["inventory"], "execution": "trusted-local"})
            return 0
        launcher = Launcher()
        if args.operation == "authorize":
            emit(launcher.authorize(args.project, args.feature, args.root))
        elif args.operation == "authorize-local":
            evidence = Path(args.fixture_evidence).absolute()
            require(not any(p.is_symlink() for p in (evidence.parent, *evidence.parent.parents)),
                    "invalid_path", "Linked fixture evidence paths are forbidden")
            value = parse_json(read_input(evidence.parent, evidence.name))
            emit(launcher.authorize_local(args.project, args.feature, args.root, args.bundle_root,
                                          args.api_input, args.configuration_input, value))
        elif args.operation == "authorize-local-dispatch":
            emit(launcher.authorize_local_dispatch(args.project, args.feature, args.slice,
                                                   args.dispatch, args.authorization))
        elif args.operation == "status":
            emit(launcher.status(args.project, args.feature))
        elif args.operation == "local-stop":
            emit(launcher.local_stop(args.project, args.feature, args.run))
        else:
            with launcher.coordinator(args.project, args.feature, args.coordinator) as session:
                emit({"operation": "coordinator_opened", "project_id": args.project, "feature_id": args.feature})
                for line in sys.stdin:
                    try:
                        require(len(line) <= 16384, "invalid_input", "Request exceeds 16 KiB")
                        request = parse_json(line)
                        require(isinstance(request, dict), "invalid_input", "Expected request object")
                        if request.get("operation") == "claim":
                            fields(request, ("operation", "slice_id", "run_id", "authorization_id"), "claim")
                            emit(session.claim(request["slice_id"], request["run_id"], request["authorization_id"]))
                        elif request.get("operation") == "local-claim":
                            fields(request, ("operation", "slice_id", "run_id", "authorization_id", "dispatch_id",
                                             "baseline", "execution"), "local-claim")
                            require(request["execution"] == "trusted-local", "execution_mismatch", "Local requests require trusted-local execution")
                            emit(session.claim_local(request["slice_id"], request["run_id"], request["authorization_id"],
                                                     request["dispatch_id"], request["baseline"]))
                        elif request.get("operation") == "status":
                            fields(request, ("operation",), "status")
                            emit(launcher.status(args.project, args.feature))
                        elif request.get("operation") in ("local-prepare", "local-fixture-check", "local-stop"):
                            fields(request, ("operation", "run_id"), request["operation"])
                            operation = {"local-prepare": session.local_prepare,
                                         "local-fixture-check": session.local_fixture_check,
                                         "local-stop": session.local_stop}[request["operation"]]
                            emit(operation(request["run_id"]))
                        elif request.get("operation") == "baseline":
                            fields(request, ("operation", "run_id"), "baseline")
                            emit(session.baseline(request["run_id"]))
                        elif request.get("operation") == "proxy-check":
                            fields(request, ("operation", "run_id"), "proxy-check")
                            emit(session.proxy_check(request["run_id"]))
                        elif request.get("operation") in ("environment-plan", "environment-check"):
                            fields(request, ("operation", "run_id"), request["operation"])
                            operation = session.environment_plan if request["operation"] == "environment-plan" else session.environment_check
                            emit(operation(request["run_id"]))
                        else:
                            raise RoutineError("unsupported_operation", "Only typed Coordinator operations are available")
                    except (RoutineError, OSError) as exc:
                        emit(error(exc))
        return 0
    except (RoutineError, OSError) as exc:
        emit(error(exc))
        return 1
