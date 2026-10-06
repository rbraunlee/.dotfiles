"""Strict v1 planning/profile contracts; all paths enter through trusted onboarding."""
import hashlib
import ipaddress
import json
import math
import re
from pathlib import Path, PurePosixPath


class RoutineError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def require(condition, code, message):
    if not condition:
        raise RoutineError(code, message)


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value),
            "invalid_id", "Identifiers must be 1–64 letters, numbers, underscores or hyphens")
    return value


def fields(value, names, label):
    require(isinstance(value, dict) and set(value) == set(names),
            "invalid_input", f"{label}: expected fields {', '.join(names)}")


def sequence(value, label, nonempty=False):
    require(isinstance(value, list) and (not nonempty or value),
            "invalid_input", f"{label}: expected {'nonempty ' if nonempty else ''}list")
    return value


def unique_ids(value, label, nonempty=False):
    sequence(value, label, nonempty)
    for item in value:
        identifier(item)
    require(len(value) == len(set(value)), "invalid_input", f"{label}: duplicate IDs")
    return value


def text(value, label):
    require(isinstance(value, str) and value and "\x00" not in value,
            "invalid_input", f"{label}: expected nonempty text without NUL")
    return value


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def hash_value(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value),
            "invalid_input", "Expected lowercase SHA-256")
    return value


def parse_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "invalid_json", f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(_):
        raise RoutineError("invalid_json", "Non-finite JSON numbers are forbidden")

    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RoutineError("invalid_json", "Invalid UTF-8 JSON") from exc


def relative_path(value):
    text(value, "path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and path.parts and
            all(part not in ("..", ".git") for part in path.parts) and
            str(path) == value and "\\" not in value,
            "invalid_path", "Expected normalized project-relative path outside .git")
    return path


def project_file(root, value):
    relative = relative_path(value)
    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        require(not candidate.is_symlink(), "invalid_path", "Symlinked inputs are forbidden")
    require(candidate.is_file(), "missing_input", f"Missing input: {value}")
    return candidate


def read_input(root, value):
    with project_file(root, value).open("rb") as stream:
        data = stream.read(4 * 1024 * 1024 + 1)
    require(len(data) <= 4 * 1024 * 1024, "invalid_input", "Planning input exceeds 4 MiB")
    try:
        data.decode("utf-8")
    except UnicodeError as exc:
        raise RoutineError("invalid_input", "Planning inputs must be UTF-8") from exc
    return data


def positive(value, label):
    require(type(value) is int and value > 0, "invalid_profile", f"{label}: expected positive integer")


def command(value, max_seconds):
    fields(value, ("argv", "timeout_seconds"), "command")
    for arg in sequence(value["argv"], "argv", nonempty=True):
        text(arg, "argument")
    positive(value["timeout_seconds"], "command timeout")
    require(value["timeout_seconds"] <= max_seconds, "invalid_profile", "Command deadline exceeds profile limit")


def resource_limits(resources):
    fields(resources, ("cpus", "memory_mb", "pids", "disk_mb", "log_mb", "command_seconds"), "resources")
    cpus = resources["cpus"]
    require((type(cpus) is int and cpus > 0) or
            (type(cpus) is float and math.isfinite(cpus) and cpus > 0),
            "invalid_profile", "cpus must be finite and positive")
    for key in set(resources) - {"cpus"}:
        positive(resources[key], key)


def validate_profile(profile):
    require(isinstance(profile, dict), "invalid_profile", "Expected profile object")
    names = ("version", "commands", "services", "mounts", "network", "credential_refs",
             "providers", "resources", "budgets", "qa")
    fields(profile, names + (("runtime",) if profile.get("version") in (2, 3) else ()) +
           (("credential_bindings",) if profile.get("version") == 3 else ()), "profile")
    require(type(profile["version"]) is int and profile["version"] in (1, 2, 3),
            "invalid_profile", "Unsupported profile version")
    if profile["version"] >= 2:
        runtime = profile["runtime"]
        fields(runtime, ("image", "opencode_version"), "runtime")
        require(isinstance(runtime["image"], str) and
                re.fullmatch(r"sha256:[0-9a-f]{64}", runtime["image"]),
                "invalid_profile", "Runtime image must be an exact local Docker image ID; tags and pulls are forbidden")
        require(runtime["opencode_version"] == "2.0.22", "invalid_profile", "M2 targets OpenCode V2.0.22 only; qualification remains required")
    resources = profile["resources"]
    resource_limits(resources)
    budgets = profile["budgets"]
    fields(budgets, ("slice_seconds", "inactivity_seconds", "integration_seconds", "repairs"), "budgets")
    for key in ("slice_seconds", "inactivity_seconds", "integration_seconds"):
        positive(budgets[key], key)
    require(type(budgets["repairs"]) is int and 0 <= budgets["repairs"] <= 2,
            "invalid_profile", "Repair budget must be between zero and two")
    commands = profile["commands"]
    fields(commands, ("setup", "checks"), "commands")
    for entry in sequence(commands["setup"], "setup"):
        command(entry, resources["command_seconds"])
    require(isinstance(commands["checks"], dict) and commands["checks"],
            "invalid_profile", "At least one named baseline check is required")
    for name, entry in commands["checks"].items():
        identifier(name)
        command(entry, resources["command_seconds"])
    refs = unique_ids(profile["credential_refs"], "credential references")
    provider_ids = []
    for provider in sequence(profile["providers"], "providers"):
        fields(provider, ("id", "credential_ref") + (("domains",) if profile["version"] == 3 else ()), "provider")
        provider_ids.append(identifier(provider["id"]))
        require(provider["credential_ref"] in refs, "invalid_profile", "Unknown provider credential reference")
    unique_ids(provider_ids, "providers")
    service_ids = []
    for service in sequence(profile["services"], "services"):
        fields(service, ("id", "image") + (("user", "ports", "readiness", "resources", "tmpfs") if profile["version"] == 3 else ()), "service")
        service_ids.append(identifier(service["id"]))
        text(service["image"], "image")
    unique_ids(service_ids, "services")
    mount_targets = []
    for mount in sequence(profile["mounts"], "mounts"):
        fields(mount, ("source", "target", "read_only") + (("sha256",) if profile["version"] >= 2 else ()), "mount")
        if profile["version"] >= 2:
            hash_value(mount["sha256"])
        relative_path(mount["source"])
        target = PurePosixPath(text(mount["target"], "mount target"))
        require(target.is_absolute() and str(target) == mount["target"] and ".." not in target.parts
                and target.is_relative_to("/inputs") and target != PurePosixPath("/inputs")
                and mount["read_only"] is True,
                "invalid_profile", "Mounts must be read-only input files below /inputs")
        require(not any(target.is_relative_to(other) or other.is_relative_to(target) for other in mount_targets),
                "invalid_profile", "Input mount targets must not duplicate or overlap")
        mount_targets.append(target)
    network = profile["network"]
    proxy_fields = ("proxy",) if profile["version"] == 3 or profile["version"] == 2 and isinstance(network, dict) and "proxy" in network else ()
    fields(network, ("allowed_domains",) + proxy_fields + (("dns_servers",) if profile["version"] == 3 else ()), "network")
    if proxy_fields:
        limits = network["proxy"]
        fields(limits, ("max_connections", "request_seconds", "idle_seconds", "tunnel_seconds", "max_tunnel_bytes"), "proxy limits")
        for key, value in limits.items():
            positive(value, "proxy " + key)
        require(limits["max_connections"] <= resources["pids"] and
                limits["request_seconds"] <= resources["command_seconds"] and
                all(limits[key] <= budgets["slice_seconds"] for key in ("request_seconds", "idle_seconds", "tunnel_seconds")),
                "invalid_profile", "Proxy limits exceed approved process/command/runtime budgets")
    domains = sequence(profile["network"]["allowed_domains"], "allowed domains")
    for domain in domains:
        text(domain, "domain")
        require(re.fullmatch(r"(?=.{1,253}$)[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?)+", domain),
                "invalid_profile", "Egress requires explicit DNS names, not URLs or wildcards")
        try:
            ipaddress.ip_address(domain)
        except ValueError:
            pass
        else:
            raise RoutineError("invalid_profile", "IP egress rules are forbidden")
        require(not domain.endswith((".localhost", ".local", ".internal")),
                "invalid_profile", "Local egress names are forbidden")
    require(len(domains) == len(set(domains)), "invalid_profile", "Duplicate domains")
    qa = profile["qa"]
    fields(qa, ("kind", "start"), "qa")
    require(qa["kind"] in ("none", "command", "browser"), "invalid_profile", "Unknown QA kind")
    if qa["kind"] == "none":
        require(qa["start"] is None, "invalid_profile", "Disabled QA cannot have a start command")
    else:
        command(qa["start"], resources["command_seconds"])
    if profile["version"] == 3:
        from .policy import validate_environment_profile

        validate_environment_profile(profile)


def load_package(root, feature_id):
    """Read, validate and snapshot the user-approved fixed-path manifest."""
    identifier(feature_id)
    manifest_path = f".opencode/routine/features/{feature_id}/approval.json"
    manifest_data = read_input(root, manifest_path)
    manifest = parse_json(manifest_data)
    fields(manifest, ("version", "feature_id", "spec", "tickets", "profile_sha256",
                      "bundle_sha256", "baseline"), "approval")
    require(type(manifest["version"]) is int and manifest["version"] == 1,
            "invalid_input", "Unsupported approval version")
    require(identifier(manifest["feature_id"]) == feature_id, "identity_conflict", "Manifest feature ID mismatch")
    hash_value(manifest["bundle_sha256"])
    fields(manifest["baseline"], ("commit", "branch"), "baseline")
    baseline = manifest["baseline"]
    require(isinstance(baseline["commit"], str) and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", baseline["commit"]),
            "invalid_input", "Baseline must be an exact Git object ID")
    require(isinstance(baseline["branch"], str) and
            re.fullmatch(r"refs/heads/features/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", baseline["branch"]),
            "invalid_input", "Expected feature branch under refs/heads/features/")
    snapshots = {manifest_path: manifest_data.decode()}

    def document(entry):
        hash_value(entry["sha256"])
        relative_path(entry["path"])
        require(entry["path"] not in snapshots and entry["path"] != ".opencode/routine/project.json",
                "invalid_input", "Planning document paths must be distinct")
        data = read_input(root, entry["path"])
        require(digest(data) == entry["sha256"], "changed_input", f"Hash mismatch: {entry['path']}")
        snapshots[entry["path"]] = data.decode()
        return data.decode()

    spec = manifest["spec"]
    fields(spec, ("path", "sha256", "criteria"), "spec")
    criteria = unique_ids(spec["criteria"], "spec criteria", nonempty=True)
    spec_text = document(spec)
    anchors = re.findall(r"<!-- criterion: ([A-Za-z0-9][A-Za-z0-9_-]{0,63}) -->", spec_text)
    require(len(anchors) == len(set(anchors)) and set(anchors) == set(criteria),
            "unresolved_criteria", "Spec criterion markers must match the complete manifest criterion list")
    tickets = sequence(manifest["tickets"], "tickets", nonempty=True)
    graph = {}
    for ticket in tickets:
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
    require(digest(profile_data) == hash_value(manifest["profile_sha256"]),
            "changed_input", "Profile hash mismatch")
    profile = parse_json(profile_data)
    validate_profile(profile)
    snapshots[".opencode/routine/project.json"] = profile_data.decode()
    package = {"manifest": manifest, "profile": profile, "snapshots": snapshots}
    if profile["version"] >= 2 and profile["mounts"]:
        from .inputs import describe_mounts

        package["mounts"] = describe_mounts(root, profile["mounts"], profile["resources"]["disk_mb"] * 1024 * 1024,
                                            timeout=profile["resources"]["command_seconds"])
    else:
        for mount in profile["mounts"]:
            project_file(root, mount["source"])
    return package
