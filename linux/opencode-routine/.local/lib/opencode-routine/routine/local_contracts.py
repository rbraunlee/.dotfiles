"""Strict fixture-only trusted-local contracts, separate from sandbox versions."""
from pathlib import Path
import re

from .contracts import (RoutineError, command, digest, fields, hash_value, identifier,
                        parse_json, positive, read_input, relative_path, require,
                        sequence, text, unique_ids)


def validate_profile(profile):
    """Validate local profile v4 without executing or resolving its references."""
    fields(profile, ("version", "execution", "commands", "command_limits", "budgets",
                     "concurrency", "credential_refs", "runtime", "services", "qa"), "profile")
    require(type(profile["version"]) is int and profile["version"] == 4,
            "invalid_profile", "Unsupported local profile version")
    require(profile["execution"] == "trusted-local",
            "invalid_profile", "Local profile requires trusted-local execution")

    limits = profile["command_limits"]
    fields(limits, ("command_seconds", "input_bytes", "output_bytes"), "command limits")
    for name, value in limits.items():
        positive(value, name)
    budgets = profile["budgets"]
    fields(budgets, ("slice_seconds", "inactivity_seconds", "integration_seconds", "repairs"), "budgets")
    for name in ("slice_seconds", "inactivity_seconds", "integration_seconds"):
        positive(budgets[name], name)
    require(type(budgets["repairs"]) is int and 0 <= budgets["repairs"] <= 2,
            "invalid_profile", "Repair budget must be between zero and two")
    fields(profile["concurrency"], ("workers_per_feature",), "concurrency")
    positive(profile["concurrency"]["workers_per_feature"], "workers per feature")

    commands = profile["commands"]
    fields(commands, ("setup", "checks"), "commands")
    max_seconds = min(limits["command_seconds"], budgets["slice_seconds"])
    for entry in sequence(commands["setup"], "setup"):
        command(entry, max_seconds)
    require(isinstance(commands["checks"], dict) and commands["checks"],
            "invalid_profile", "At least one named baseline check is required")
    for name, entry in commands["checks"].items():
        identifier(name)
        command(entry, max_seconds)

    # Identifiers prevent embedding values, not production access: development/test/
    # model scope is an approval obligation that cannot be established from a name.
    unique_ids(profile["credential_refs"], "credential references")
    runtime = profile["runtime"]
    fields(runtime, ("opencode_version", "api_sha256", "configuration_sha256", "connection_ref"), "runtime")
    text(runtime["opencode_version"], "OpenCode version")
    hash_value(runtime["api_sha256"])
    hash_value(runtime["configuration_sha256"])
    identifier(runtime["connection_ref"])

    require(sequence(profile["services"], "services") == [],
            "invalid_profile", "Local fixture services must be empty")
    fields(profile["qa"], ("kind", "start"), "qa")
    require(profile["qa"]["kind"] == "none" and profile["qa"]["start"] is None,
            "invalid_profile", "Local fixture QA must be disabled")


def _validate_baseline(baseline):
    fields(baseline, ("commit", "branch"), "baseline")
    require(isinstance(baseline["commit"], str) and
            re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", baseline["commit"]),
            "invalid_input", "Baseline must be an exact Git object ID")
    require(isinstance(baseline["branch"], str) and
            re.fullmatch(r"refs/heads/features/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", baseline["branch"]),
            "invalid_input", "Expected feature branch under refs/heads/features/")


def load_package(root, feature_id):
    """Read and snapshot approval v2/profile v4; never authorize legacy inputs."""
    root = Path(root)
    identifier(feature_id)
    manifest_path = f".opencode/routine/features/{feature_id}/approval.json"
    manifest_data = read_input(root, manifest_path)
    manifest = parse_json(manifest_data)
    fields(manifest, ("version", "execution", "feature_id", "spec", "tickets",
                      "profile_sha256", "bundle_sha256", "baseline"), "approval")
    require(type(manifest["version"]) is int and manifest["version"] == 2,
            "invalid_input", "Unsupported local approval version")
    require(manifest["execution"] == "trusted-local",
            "invalid_input", "Local approval requires trusted-local execution")
    require(identifier(manifest["feature_id"]) == feature_id,
            "identity_conflict", "Manifest feature ID mismatch")
    hash_value(manifest["bundle_sha256"])
    hash_value(manifest["profile_sha256"])
    _validate_baseline(manifest["baseline"])
    snapshots = {manifest_path: manifest_data.decode()}

    def document(entry):
        hash_value(entry["sha256"])
        relative_path(entry["path"])
        require(entry["path"] not in snapshots and entry["path"] != ".opencode/routine/project.json",
                "invalid_input", "Planning document paths must be distinct")
        data = read_input(root, entry["path"])
        require(digest(data) == entry["sha256"], "changed_input", "Planning document hash mismatch")
        snapshots[entry["path"]] = data.decode()
        return data.decode()

    # Keep the historical spec/graph semantics, without routing a local package
    # through its sandbox validator or weakening historical authorization rules.
    spec = manifest["spec"]
    fields(spec, ("path", "sha256", "criteria"), "spec")
    criteria = unique_ids(spec["criteria"], "spec criteria", nonempty=True)
    spec_text = document(spec)
    anchors = re.findall(r"<!-- criterion: ([A-Za-z0-9][A-Za-z0-9_-]{0,63}) -->", spec_text)
    require(len(anchors) == len(set(anchors)) and set(anchors) == set(criteria),
            "unresolved_criteria", "Spec criterion markers must match the complete manifest criterion list")
    graph = {}
    for ticket in sequence(manifest["tickets"], "tickets", nonempty=True):
        fields(ticket, ("slice_id", "path", "sha256", "criteria", "dependencies"), "ticket")
        slice_id = identifier(ticket["slice_id"])
        require(slice_id not in graph, "invalid_input", "Duplicate slice ID")
        applicable = unique_ids(ticket["criteria"], "ticket criteria", nonempty=True)
        require(set(applicable) <= set(criteria), "unresolved_criteria", "Ticket references unknown criteria")
        graph[slice_id] = unique_ids(ticket["dependencies"], "dependencies")
        document(ticket)
    for deps in graph.values():
        require(set(deps) <= set(graph), "invalid_graph", "Unknown slice dependency")
    visiting, visited = set(), set()

    def visit(slice_id):
        require(slice_id not in visiting, "invalid_graph", "Cyclic dependency graph")
        if slice_id in visited:
            return
        visiting.add(slice_id)
        for dep in graph[slice_id]:
            visit(dep)
        visiting.remove(slice_id)
        visited.add(slice_id)

    try:
        for slice_id in graph:
            visit(slice_id)
    except RecursionError as exc:
        raise RoutineError("invalid_graph", "Dependency graph exceeds supported nesting depth") from exc

    profile_data = read_input(root, ".opencode/routine/project.json")
    require(digest(profile_data) == manifest["profile_sha256"], "changed_input", "Profile hash mismatch")
    profile = parse_json(profile_data)
    validate_profile(profile)
    snapshots[".opencode/routine/project.json"] = profile_data.decode()
    return {"manifest": manifest, "profile": profile, "snapshots": snapshots}


def validate_fixture_evidence(value, package):
    """Validate approved baseline references, not their execution or semantic scope.

    ``package`` must be an already validated local package. The unchanged evidence
    is returned for the launcher's immutable authorization record.
    """
    fields(value, ("version", "execution", "baseline", "profile_sha256", "mutations_approved", "checks"),
           "fixture evidence")
    require(type(value["version"]) is int and value["version"] == 1,
            "invalid_input", "Unsupported fixture evidence version")
    require(value["execution"] == "trusted-local",
            "invalid_input", "Fixture evidence requires trusted-local execution")
    require(value["mutations_approved"] is True,
            "unapproved", "Fixture mutations require approval")
    _validate_baseline(value["baseline"])
    require(value["baseline"] == package["manifest"]["baseline"],
            "changed_input", "Fixture baseline mismatch")
    hash_value(value["profile_sha256"])
    require(value["profile_sha256"] == package["manifest"]["profile_sha256"],
            "changed_input", "Fixture profile hash mismatch")
    fields(value["checks"], tuple(package["profile"]["commands"]["checks"]), "fixture checks")
    for entry in value["checks"].values():
        require(isinstance(entry, dict), "invalid_input", "Expected fixture check object")
        outcome = entry.get("outcome")
        require(outcome in ("passed", "exception"),
                "invalid_input", "Fixture checks require passing evidence or an approved exception")
        names = ("outcome", "evidence_ref")
        if outcome == "exception":
            names += ("failure_ref", "scope_ref", "approval_ref")
        fields(entry, names, "fixture check")
        for name in names[1:]:
            identifier(entry[name])
    return value
