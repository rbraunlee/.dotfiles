"""Fail-closed, offline Compose baseline adapter; no project Compose fragments."""
import io
from pathlib import Path
import tarfile
import time
import uuid

from .contracts import RoutineError, canonical, digest, fields, hash_value, parse_json, require
from .inputs import snapshot_name
from .process import run_bounded


ASSET_NAMES = ("Dockerfile", "worker.py", "opencode.json", "proxy.py")


def worker_assets():
    return Path(__file__).resolve().parents[3] / "share/opencode-routine/worker"


def bundle_identity(root=None):
    root = root or worker_assets()
    return digest(canonical({name: digest((root / name).read_bytes()) for name in ASSET_NAMES}))


def offline_profile(profile):
    require(profile["version"] == 2, "runtime_missing", "Launch requires profile v2 with a pinned runtime image")
    require(not profile["network"]["allowed_domains"] and not profile["services"] and
            not profile["credential_refs"] and not profile["providers"],
            "policy_unavailable", "M2 offline path cannot grant egress, services, providers or credentials")


def require_quota_backend(info):
    # Qualification on Docker 29's containerd overlayfs backend demonstrated that
    # storage_opt.size was accepted but ignored. Admission must not confuse option
    # presence with enforcement. The current path supports only classic overlay2
    # on XFS; Docker also rejects size at creation when project quotas are missing.
    require(isinstance(info, dict), "invalid_runtime", "Expected Docker daemon information")
    rows = info.get("DriverStatus") or []
    require(isinstance(rows, list) and all(isinstance(row, list) and len(row) == 2 for row in rows),
            "invalid_runtime", "Malformed Docker storage driver information")
    backing = next((row[1] for row in rows if row[0] == "Backing Filesystem"), None)
    require(info.get("Driver") == "overlay2" and backing == "xfs",
            "disk_quota_unavailable", "This Docker storage backend is not qualified for writable-layer size quotas; no sandbox will start")


def require_resource_support(info):
    require(isinstance(info, dict), "invalid_runtime", "Expected Docker daemon information")
    require(info.get("CgroupVersion") == "2" and
            all(info.get(key) is True for key in ("MemoryLimit", "SwapLimit", "PidsLimit", "CpuCfsPeriod", "CpuCfsQuota")),
            "resource_limits_unavailable", "Runtime requires cgroup v2 CPU, memory, swap and PID limit support; no sandbox will start")


def compose_document(profile, handoff, artifact_id):
    offline_profile(profile)
    limits = profile["resources"]
    volumes = [{"type": "bind", "source": str(handoff), "target": "/handoff", "read_only": True,
                "bind": {"create_host_path": False}}]
    volumes += [{"type": "bind", "source": str(Path(handoff) / "mounts" / snapshot_name(index)),
                 "target": mount["target"], "read_only": True, "bind": {"create_host_path": False}}
                for index, mount in enumerate(profile["mounts"], 1)]
    return {"services": {"worker": {
        "image": profile["runtime"]["image"], "pull_policy": "never",
        "container_name": "routine-" + artifact_id[:32],
        "entrypoint": ["python3", "-B", "/opt/routine/bundle/worker.py"],
        "user": "10001:10001", "working_dir": "/control", "init": True,
        "network_mode": "none", "restart": "no", "privileged": False,
        "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
        "cpus": limits["cpus"], "mem_limit": f"{limits['memory_mb']}m",
        "memswap_limit": f"{limits['memory_mb']}m", "pids_limit": limits["pids"],
        # Require actual Docker writable-layer quota support; never drop this on failure.
        "storage_opt": {"size": f"{limits['disk_mb']}M"},
        "logging": {"driver": "local", "options": {"max-size": f"{limits['log_mb']}m", "max-file": "1", "compress": "false"}},
        "environment": {"HOME": "/home/worker", "XDG_CONFIG_HOME": "/opt/routine/config",
                        "XDG_STATE_HOME": "/home/worker/.state", "XDG_DATA_HOME": "/home/worker/.data",
                        "XDG_CACHE_HOME": "/home/worker/.cache", "GIT_CONFIG_NOSYSTEM": "1",
                        "GIT_CONFIG_GLOBAL": "/opt/routine/gitconfig", "GIT_TEMPLATE_DIR": "/opt/routine/empty-template",
                        "GIT_TERMINAL_PROMPT": "0", "GIT_NO_LAZY_FETCH": "1",
                        "PYTHONDONTWRITEBYTECODE": "1"},
        "volumes": volumes,
        # Private preparation nonce distinguishes even matching names/artifact IDs
        # from a retained container created by another state root or earlier run.
        "labels": {"routine.artifact-id": artifact_id, "routine.launch-id": uuid.uuid4().hex},
    }}}


def read_evidence_archive(data, max_bytes):
    """Never extract worker-provided tar paths, links, devices or checkout files."""
    require(len(data) <= max_bytes + 65536, "output_limit", "Evidence archive is oversized")
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
            members = archive.getmembers()
            require(len(members) == 1 and members[0].name == "evidence.json" and
                    members[0].isfile() and 0 < members[0].size <= max_bytes,
                    "invalid_evidence", "Expected exactly one bounded regular evidence.json file")
            stream = archive.extractfile(members[0])
            with stream:
                return parse_json(stream.read(max_bytes + 1))
    except (tarfile.TarError, EOFError) as exc:
        raise RoutineError("invalid_evidence", "Malformed evidence archive") from exc


class DockerCompose:
    def __init__(self, run=run_bounded, sleep=time.sleep, monotonic=time.monotonic):
        self.run = run
        self.sleep = sleep
        self.monotonic = monotonic
        self.containers = {}

    def docker(self, args, timeout, max_bytes=1024 * 1024):
        return self.run(["/usr/bin/docker", "--host", "unix:///var/run/docker.sock", *args],
                        timeout=timeout, max_bytes=max_bytes)

    def preflight(self, profile, bundle_sha256, timeout):
        offline_profile(profile)
        info = parse_json(self.docker(["info", "--format", "{{json .}}"], timeout))
        require_quota_backend(info)
        require_resource_support(info)
        self.require_image(profile, bundle_sha256, timeout)

    def require_image(self, profile, bundle_sha256, timeout):
        images = parse_json(self.docker(["image", "inspect", profile["runtime"]["image"]], timeout))
        require(isinstance(images, list) and len(images) == 1, "invalid_runtime", "Expected one local worker image")
        image = images[0]
        require(image.get("Id") == profile["runtime"]["image"], "invalid_runtime", "Worker image identity mismatch")
        labels = image.get("Config", {}).get("Labels") or {}
        require(labels.get("routine.bundle-sha256") == bundle_sha256 and
                labels.get("routine.opencode-version") == profile["runtime"]["opencode_version"],
                 "invalid_runtime", "Worker image labels do not match the authorized bundle/release")

    def preflight_proxy(self, profile, bundle_sha256, artifact_id, timeout):
        from .proxy import proxy_policy

        proxy_policy(profile)
        require(bundle_sha256 == bundle_identity(), "invalid_runtime", "Proxy check requires the approved local worker assets")
        deadline = self.monotonic() + timeout
        info = parse_json(self.docker(["info", "--format", "{{json .}}"], timeout))
        require_resource_support(info)
        remaining = deadline - self.monotonic()
        require(remaining > 0, "command_timeout", "Proxy preflight deadline exhausted")
        # No writable layer: this check is not a quota fallback for a worker checkout.
        self.require_image(profile, bundle_sha256, remaining)
        remaining = deadline - self.monotonic()
        require(remaining > 0, "command_timeout", "Proxy preflight deadline exhausted")
        # Compose up can replace an old stopped container. Retention and interrupted
        # runs must never be silently adopted/replaced, even under another state root.
        from .contracts import hash_value
        hash_value(artifact_id)
        existing = self.docker(["ps", "--all", "--filter", "name=^/routine-proxy-" + artifact_id[:32] + "$",
                                "--format", "{{.ID}}"], remaining)
        require(not existing.strip(), "recovery_required", "An existing proxy container requires deliberate recovery")

    def start_proxy(self, directory, artifact_id, timeout):
        self.compose(directory, artifact_id, ["up", "--detach", "--no-build", "--pull", "never", "proxy"], timeout)

    def inspect_proxy(self, artifact_id, timeout):
        from .contracts import hash_value

        hash_value(artifact_id)
        rows = parse_json(self.docker(["inspect", "routine-proxy-" + artifact_id[:32]], timeout))
        require(isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict),
                "invalid_runtime", "Expected exactly one proxy container")
        value = rows[0]
        require(isinstance(value.get("Config"), dict) and isinstance(value["Config"].get("Labels"), dict) and
                isinstance(value.get("State"), dict), "invalid_runtime", "Malformed proxy container inspection")
        require(value.get("Config", {}).get("Labels", {}).get("routine.artifact-id") == artifact_id and
                value.get("Name") == "/routine-proxy-" + artifact_id[:32],
                "invalid_runtime", "Proxy container identity mismatch")
        return value

    def wait_proxy_ready(self, artifact_id, profile, policy_sha256, timeout):
        from .proxy import proxy_healthcheck

        deadline = self.monotonic() + timeout
        while True:
            remaining = deadline - self.monotonic()
            require(remaining > 0, "command_timeout", "Proxy readiness deadline exhausted")
            value = self.inspect_proxy(artifact_id, remaining)
            config, host = value.get("Config", {}), value.get("HostConfig", {})
            labels = config.get("Labels", {})
            mounts = value.get("Mounts", [])
            require(isinstance(host, dict) and isinstance(config.get("Healthcheck"), dict) and
                    isinstance(host.get("RestartPolicy"), dict) and isinstance(host.get("SecurityOpt"), list) and
                    isinstance(mounts, list) and all(isinstance(mount, dict) for mount in mounts) and
                    isinstance(value["State"].get("Health"), dict),
                    "invalid_runtime", "Malformed proxy policy/health inspection")
            limits = profile["resources"]
            require(value.get("Image") == profile["runtime"]["image"] and config.get("User") == "10001:10001" and
                    labels.get("routine.proxy-policy-sha256") == policy_sha256 and
                    labels.get("routine.proxy-mode") == "offline-check" and
                    config.get("Entrypoint") == ["python3", "-I", "-B", "/opt/routine/bundle/proxy.py", "/policy/proxy.json"] and
                    config.get("Healthcheck", {}).get("Test") == proxy_healthcheck(policy_sha256, bundle_identity()) and
                    host.get("NetworkMode") == "none" and host.get("ReadonlyRootfs") is True and
                    host.get("Privileged") is False and not host.get("CapAdd") and host.get("CapDrop") == ["ALL"] and
                    any(option in ("no-new-privileges", "no-new-privileges:true") for option in host.get("SecurityOpt", [])) and
                    not host.get("PortBindings") and not host.get("Devices") and not host.get("ExtraHosts") and
                    not host.get("PidMode") and host.get("RestartPolicy", {}).get("Name") == "no" and
                    host.get("Memory") == limits["memory_mb"] * 1024 * 1024 and
                    host.get("MemorySwap") == limits["memory_mb"] * 1024 * 1024 and
                    host.get("PidsLimit") == limits["pids"] and host.get("NanoCpus") == int(limits["cpus"] * 10**9) and
                    host.get("LogConfig") == {"Type": "local", "Config": {"max-size": f"{limits['log_mb']}m", "max-file": "1", "compress": "false"}} and
                    len(mounts) == 1 and mounts[0].get("Type") == "bind" and
                    mounts[0].get("Destination") == "/policy/proxy.json" and mounts[0].get("RW") is False,
                    "invalid_runtime", "Effective proxy configuration differs from the offline policy")
            state = value.get("State", {})
            require(state.get("Running") is True, "proxy_start_failed", "Proxy stopped before readiness")
            status = state.get("Health", {}).get("Status")
            require(status in ("starting", "healthy", "unhealthy"), "invalid_runtime", "Missing proxy health status")
            require(status != "unhealthy", "proxy_readiness_failed", "Proxy policy/listener readiness failed")
            require(self.monotonic() < deadline, "command_timeout", "Proxy readiness response exceeded its deadline")
            if status == "healthy":
                return
            self.sleep(min(0.1, deadline - self.monotonic()))

    def stop_proxy(self, directory, artifact_id, timeout):
        deadline = self.monotonic() + timeout
        # Verify ownership before stopping a name that might not belong to this run.
        self.inspect_proxy(artifact_id, timeout)
        remaining = deadline - self.monotonic()
        require(remaining > 0, "command_timeout", "Proxy stop deadline exhausted")
        self.compose(directory, artifact_id, ["stop", "--timeout", "5", "proxy"], remaining)
        remaining = deadline - self.monotonic()
        require(remaining > 0, "command_timeout", "Proxy stop confirmation deadline exhausted")
        value = self.inspect_proxy(artifact_id, remaining)
        require(self.monotonic() < deadline and value.get("State", {}).get("Running") is False,
                "stop_unconfirmed", "Proxy container stopping was not confirmed")
        # No down/rm/prune: retain the policy, stopped container and evidence.

    def compose(self, directory, artifact_id, args, timeout):
        return self.docker(["compose", "--project-directory", str(directory), "--env-file", "/dev/null",
                            "--project-name", "routine-" + artifact_id[:32], "--file", str(directory / "compose.json"), *args], timeout)

    def start(self, directory, artifact_id, timeout):
        hash_value(artifact_id)
        deadline = self.monotonic() + timeout
        existing = self.docker(["ps", "--all", "--filter", "name=^/routine-" + artifact_id[:32] + "$",
                                "--format", "{{.ID}}"], timeout)
        require(not existing.strip(), "recovery_required", "An existing worker container requires deliberate recovery")
        # Never let Compose up replace a retained checkout. The nonce check also
        # rejects a container appearing between the absence check and creation.
        self.compose(directory, artifact_id, ["create", "--no-recreate", "--no-build", "--pull", "never", "worker"],
                     deadline - self.monotonic())
        value = self.owned_worker(directory, artifact_id, deadline - self.monotonic())
        self.containers[artifact_id] = value["Id"]
        self.docker(["start", value["Id"]], deadline - self.monotonic())
        require(self.monotonic() < deadline, "command_timeout", "Worker startup exceeded its deadline")
        return value["Id"]

    def owned_worker(self, directory, artifact_id, timeout):
        hash_value(artifact_id)
        document = parse_json((Path(directory) / "compose.json").read_bytes())
        expected = document["services"]["worker"]
        launch_id = expected["labels"]["routine.launch-id"]
        require(isinstance(launch_id, str) and len(launch_id) == 32 and
                all(character in "0123456789abcdef" for character in launch_id),
                "invalid_runtime", "Missing worker preparation identity")
        rows = parse_json(self.docker(["inspect", "routine-" + artifact_id[:32]], timeout))
        require(isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict),
                "invalid_runtime", "Expected exactly one worker container")
        value = rows[0]
        require(isinstance(value.get("Config"), dict) and isinstance(value.get("State"), dict) and
                isinstance(value["Config"].get("Labels"), dict), "invalid_runtime", "Malformed worker identity")
        hash_value(value.get("Id"))
        labels = value["Config"]["Labels"]
        require(value.get("Name") == "/routine-" + artifact_id[:32] and value.get("Image") == expected["image"] and
                labels.get("routine.artifact-id") == artifact_id and labels.get("routine.launch-id") == launch_id and
                (artifact_id not in self.containers or self.containers[artifact_id] == value["Id"]),
                "recovery_required", "Worker container does not belong to this preparation; it will not be adopted or stopped")
        return value

    def wait(self, artifact_id, timeout):
        deadline = self.monotonic() + timeout
        while True:
            remaining = deadline - self.monotonic()
            require(remaining > 0, "command_timeout", "Sandbox exceeded its total runtime budget")
            target = self.containers.get(artifact_id, "routine-" + artifact_id[:32])
            containers = parse_json(self.docker(["inspect", target], min(remaining, 15)))
            require(isinstance(containers, list) and len(containers) == 1, "invalid_runtime", "Sandbox container is missing")
            container = containers[0]
            require(container.get("Config", {}).get("Labels", {}).get("routine.artifact-id") == artifact_id,
                    "invalid_runtime", "Container ownership label mismatch")
            require(artifact_id not in self.containers or container.get("Id") == self.containers[artifact_id],
                    "invalid_runtime", "Container identity changed after creation")
            require(self.monotonic() < deadline, "command_timeout", "Worker state response exceeded its deadline")
            if not container["State"]["Running"]:
                return container["State"]["ExitCode"]
            self.sleep(min(0.1, remaining))

    def collect(self, artifact_id, max_bytes, timeout):
        hash_value(artifact_id)
        deadline = self.monotonic() + timeout
        # Docker's archive mount needs metadata headroom even for stopped-container
        # reads. The log API needs no layer mount and survives writable-layer ENOSPC.
        # Parse the entire bounded stdout stream: no tail/marker scanning that could
        # hide raw output, duplicated records or a truncated earlier failure.
        target = self.containers.get(artifact_id, "routine-" + artifact_id[:32])
        data = self.docker(["logs", target], timeout, max_bytes=max_bytes + 64)
        require(self.monotonic() < deadline, "command_timeout", "Evidence collection exceeded its deadline")
        if data.strip():
            value = parse_json(data)
            fields(value, ("routine_evidence",), "evidence transport")
            require(len(canonical(value["routine_evidence"])) <= max_bytes,
                    "output_limit", "Evidence exceeds its approved bound")
            return value["routine_evidence"]
        # Compatibility for approved older images that only wrote evidence.json.
        # Nonempty malformed logs never fall back to accepting another channel.
        archive = self.docker(["cp", target + ":/home/worker/evidence.json", "-"],
                              deadline - self.monotonic(), max_bytes=max_bytes + 65536)
        require(self.monotonic() < deadline, "command_timeout", "Evidence collection exceeded its deadline")
        return read_evidence_archive(archive, max_bytes)

    def stop(self, directory, artifact_id, timeout=20):
        deadline = self.monotonic() + timeout
        value = self.owned_worker(directory, artifact_id, timeout)
        self.containers[artifact_id] = value["Id"]
        # Address the verified immutable ID, not a mutable Compose/name lookup.
        self.docker(["stop", "--time", "10", value["Id"]], deadline - self.monotonic())
        self.wait(artifact_id, deadline - self.monotonic())
        require(self.monotonic() < deadline, "stop_unconfirmed", "Worker stopping exceeded its confirmation deadline")
        # Retain the stopped container's independent checkout and raw diagnostics.
        # Deliberately no compose down, rm, prune, volume deletion or host extraction.
