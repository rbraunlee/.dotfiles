"""Concrete, injectable bounded service lifecycle. Production Environment stays disabled."""
from copy import deepcopy
import ipaddress
import math
import os
from pathlib import Path
import stat
import time
import uuid

from .compose import DockerCompose, require_quota_backend, require_resource_support
from .contracts import canonical, digest, fields, hash_value, parse_json, require, RoutineError
from .credential_sources import normalized_binding, private_directory
from .policy import credential_target
from .proxy import retained_file, sync_directory


def service_identity(component):
    # Fixed, DNS-safe and case-sensitive-ID collision resistant. Not user fragments.
    return "service-" + digest(component.encode())[:24]


def service_config(document):
    return next(iter(document["services"].values()))


def service_document(plan, service, attachments, volumes, nonce):
    component = "service:" + service["id"]
    resources = service["resources"]
    uid, gid = service["user"].split(":")
    mounts = [f"{item['target']}:rw,noexec,nosuid,nodev,size={item['size_mb'] * 1048576},mode=0700,uid={uid},gid={gid}"
              for item in service["tmpfs"]]
    name = "routine-service-" + plan["artifact_id"][:24] + "-" + digest(component.encode())[:16]
    network = attachments[0]
    return {"services": {service_identity(component): {
        "container_name": name, "image": service["image"], "pull_policy": "never", "user": service["user"],
        "init": True, "read_only": True, "restart": "no", "privileged": False, "ipc": "private",
        "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"], "healthcheck": {"disable": True},
        "cpus": resources["cpus"], "mem_limit": f"{resources['memory_mb']}m",
        "memswap_limit": f"{resources['memory_mb']}m", "pids_limit": resources["pids"],
        "storage_opt": {"size": f"{resources['disk_mb']}M"},
        "logging": {"driver": "local", "options": {"max-size": f"{resources['log_mb']}m", "max-file": "1", "compress": "false"}},
        "tmpfs": mounts, "volumes": volumes, "environment": {},
        # Services do not get upstream DNS. verify_component must additionally
        # prove Docker embedded-DNS/bootstrap forwarding cannot bypass this intent.
        "dns": ["127.0.0.1"], "dns_search": ["."], "dns_opt": ["ndots:0"],
        "networks": {"internal": {"ipv4_address": network["ipv4_address"], "aliases": [service_identity(component)]}},
        "labels": {"routine.artifact-id": plan["artifact_id"], "routine.component": component,
                   "routine.launch-id": nonce, "routine.plan-sha256": digest(canonical(plan))}}},
        "networks": {"internal": {"external": True, "name": network["name"]}}}


class ServiceEnvironmentAdapter:
    """Explicit injection only: no Coordinator enable flag or production wiring.

    checkpoint(plan, component, event, metadata) must durably journal create intent,
    nonce and immutable ID. credential_path(plan, binding) is a trusted delivery
    bridge, never a Coordinator path. Its real integration remains unverified.
    Networks/proxy are entirely owned by the injected NetworkAdapter.
    """
    def __init__(self, artifact_root, network, *, checkpoint, credential_path=None, docker=None, monotonic=time.monotonic):
        require(callable(checkpoint), "policy_unavailable", "Service lifecycle requires an ownership checkpoint")
        self.root, self.network, self.checkpoint = Path(artifact_root), network, checkpoint
        self.credential_path = credential_path
        self.docker = docker or DockerCompose()
        self.monotonic = monotonic
        self.states, self.images, self.prepared, self.enforced = {}, {}, {}, set()

    def bind_host_interfaces(self, checkpoint, credential_path):
        """Coordinator-owned durable sink and delivery lookup, before preflight."""
        require(not self.prepared and not self.states and callable(checkpoint) and callable(credential_path),
                "recovery_required", "Host interfaces cannot replace an active preparation")
        self.network.checkpoint = checkpoint
        self.checkpoint = lambda plan, component, event, metadata: checkpoint({
            "event": "service-" + event, "artifact_id": plan["artifact_id"],
            "component": component, **metadata})
        self.credential_path = credential_path

    def budget(self, timeout):
        require(type(timeout) in (int, float) and math.isfinite(timeout) and timeout > 0,
                "command_timeout", "Service deadline exhausted")
        deadline = self.monotonic() + timeout
        def remaining():
            require(self.monotonic() < deadline, "command_timeout", "Service operation exceeded its deadline")
            return deadline - self.monotonic()
        return remaining

    def preflight(self, plan, timeout):
        remaining = self.budget(timeout)
        hash_value(plan["artifact_id"])
        self.network.preflight(plan, remaining())
        info = parse_json(self.docker.docker(["info", "--format", "{{json .}}"], remaining()))
        require_resource_support(info)
        require_quota_backend(info)
        images = {}
        for service in plan["services"]:
            rows = parse_json(self.docker.docker(["image", "inspect", service["image"]], remaining()))
            require(isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict) and
                    rows[0].get("Id") == service["image"] and isinstance(rows[0].get("Config"), dict),
                    "invalid_runtime", "Pinned local service image is unavailable")
            config = rows[0]["Config"]
            require(not config.get("Volumes"), "invalid_runtime", "Image-declared anonymous service volumes are unsupported")
            images[service["image"]] = deepcopy(config)
        remaining()
        plan_hash = digest(canonical(plan))
        previous = self.prepared.get(plan["artifact_id"])
        require(previous is None or previous == plan_hash, "recovery_required", "Prepared service plan changed")
        self.images.update(images)
        self.prepared[plan["artifact_id"]] = plan_hash

    def require_plan(self, plan):
        require(self.prepared.get(plan["artifact_id"]) == digest(canonical(plan)),
                "recovery_required", "Service plan is not the prepared immutable plan")

    def create_networks(self, plan, timeout):
        self.require_plan(plan)
        remaining = self.budget(timeout)
        result = self.network.create_networks(plan, remaining())
        remaining()
        return result

    def enforce_policy(self, plan, timeout):
        self.require_plan(plan)
        remaining = self.budget(timeout)
        result = self.network.enforce_policy(plan, remaining())
        remaining()
        self.enforced.add(plan["artifact_id"])
        return result

    def attachments(self, plan, component):
        values = deepcopy(self.network.component_networks(plan, component))
        require(isinstance(values, list) and len(values) == 1, "invalid_runtime", "Services require exactly one owned internal attachment")
        value = values[0]
        fields(value, ("logical_id", "network_id", "name", "ipv4_address"), "owned service attachment")
        hash_value(value["network_id"])
        expected = next((item for item in plan["networks"] if item["id"] == value["logical_id"]), None)
        require(expected is not None and expected["internal"] is True and expected["ipv6"] is False and
                component in expected["members"] and value["logical_id"] == "internal" and value["name"] == expected["name"],
                "invalid_runtime", "Service attachment differs from the approved topology")
        try:
            address = ipaddress.IPv4Address(value["ipv4_address"])
        except (ValueError, TypeError):
            raise RoutineError("invalid_runtime", "Invalid assigned service address") from None
        require(str(address) == value["ipv4_address"] and not address.is_loopback and not address.is_multicast and not address.is_unspecified,
                "invalid_runtime", "Invalid assigned service address")
        return values

    def volumes(self, plan, component, bindings):
        require(isinstance(bindings, list), "invalid_credential", "Expected scoped service deliveries")
        expected = [binding for binding in plan["credentials"] if binding["consumer"] == component]
        require(len(bindings) == len(expected), "invalid_credential", "Service credential delivery is incomplete")
        approved, seen, volumes = {binding["ref"]: binding for binding in expected}, set(), []
        for binding in bindings:
            normalized_binding(binding)
            require(binding["consumer"] == component and binding["ref"] in approved and binding["ref"] not in seen,
                    "invalid_credential", "Credential delivery belongs to another consumer")
            original = approved[binding["ref"]]
            require(binding == original, "invalid_credential", "Service delivery metadata differs from the approved binding")
            seen.add(binding["ref"])
            require(callable(self.credential_path), "policy_unavailable", "Trusted service delivery bridge is not supplied")
            source = Path(self.credential_path(plan, deepcopy(binding)))
            root = self.root / plan["artifact_id"] / "credentials"
            require(source.is_absolute() and source.is_relative_to(root) and source != root,
                    "unsafe_state", "Credential source is outside this preparation")
            relative = source.relative_to(root)
            require(".." not in relative.parts, "unsafe_state", "Unsafe service delivery path")
            fd = private_directory(root)
            leaf = None
            try:
                for part in relative.parts[:-1]:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
                    os.close(fd)
                    fd = child
                    info = os.fstat(fd)
                    require(info.st_uid == os.geteuid() and not info.st_mode & 0o077,
                            "unsafe_state", "Credential delivery ancestry is not private")
                leaf = os.open(relative.parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
                info = os.fstat(leaf)
                require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and info.st_nlink == 1 and
                        stat.S_IMODE(info.st_mode) == 0o444 and 0 < info.st_size <= binding["max_bytes"],
                        "unsafe_state", "Unsafe credential delivery file")
            finally:
                if leaf is not None:
                    os.close(leaf)
                os.close(fd)
            # Metadata only: no credential bytes or hashes are read by the adapter.
            volumes.append({"type": "bind", "source": str(source), "target": credential_target(binding["ref"], component),
                            "read_only": True, "bind": {"create_host_path": False, "propagation": "rprivate"}})
        return volumes

    def start_component(self, plan, component, credentials, timeout):
        self.require_plan(plan)
        remaining = self.budget(timeout)
        require(plan["artifact_id"] in self.enforced and component in plan["components"],
                "policy_unavailable", "Consumer startup requires approved enforced policy")
        if component == "proxy":
            require(credentials == [], "invalid_credential", "Proxy receives no credentials")
            result = self.network.start_proxy(plan, remaining())
            remaining()
            return result
        service = next((item for item in plan["services"] if "service:" + item["id"] == component), None)
        require(service is not None, "invalid_runtime", "Unknown service component")
        remaining = self.budget(min(remaining(), service["resources"]["command_seconds"]))
        key = (plan["artifact_id"], component)
        require(key not in self.states, "recovery_required", "Service preparation cannot be retried or adopted")
        attachments = self.attachments(plan, component)
        volumes = self.volumes(plan, component, credentials)
        nonce = uuid.uuid4().hex
        document = service_document(plan, service, attachments, volumes, nonce)
        name = service_config(document)["container_name"]
        existing = self.docker.docker(["ps", "--all", "--filter", "name=^/" + name + "$", "--format", "{{.ID}}"], remaining())
        require(not existing.strip(), "recovery_required", "Existing service requires deliberate recovery; it will not be replaced")
        self.checkpoint(plan, component, "create-intent", {"nonce": nonce, "image": service["image"], "plan_sha256": digest(canonical(plan))})
        remaining()
        state = {"document": document, "attachments": attachments, "container_id": None, "plan_sha256": digest(canonical(plan))}
        self.states[key] = state
        directory = self.root / plan["artifact_id"] / service_identity(component)
        # Only private run-owned directories/files. No mutable repository inputs.
        for path in (self.root, self.root / plan["artifact_id"], directory):
            path.mkdir(mode=0o700, exist_ok=True)
            fd = private_directory(path)
            os.close(fd)
        retained_file(directory / "compose.json", canonical(document), 0o600)
        sync_directory(directory)
        self.docker.compose(directory, digest((plan["artifact_id"] + component).encode()),
                            ["create", "--no-recreate", "--no-build", "--pull", "never", service_identity(component)], remaining())
        value = self.owned(plan, component, remaining())
        state["container_id"] = value["Id"]
        self.checkpoint(plan, component, "created", {"nonce": nonce, "container_id": value["Id"]})
        self.verify_service(plan, component, value)
        proof = self.network.verify_component(plan, component, value, remaining())
        require(proof is None or proof is True, "policy_unavailable", "Network adapter refused pre-start enforcement proof")
        # verify_component must raise on failed pre-start bootstrap/enforcement.
        remaining()
        self.checkpoint(plan, component, "start-intent", {"container_id": value["Id"]})
        # Recheck stopped identity/config after network enforcement, before start.
        latest = self.owned(plan, component, remaining())
        self.verify_service(plan, component, latest)
        self.docker.docker(["start", value["Id"]], remaining())
        remaining()
        return value["Id"]

    def owned(self, plan, component, timeout):
        state = self.states.get((plan["artifact_id"], component))
        require(state is not None and state["plan_sha256"] == digest(canonical(plan)), "recovery_required", "Missing immutable service preparation")
        expected = service_config(state["document"])
        target = state["container_id"] or expected["container_name"]
        rows = parse_json(self.docker.docker(["inspect", target], timeout))
        require(isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict), "invalid_runtime", "Missing owned service container")
        value = rows[0]
        hash_value(value.get("Id"))
        config = value.get("Config")
        require(isinstance(config, dict) and isinstance(config.get("Labels"), dict) and isinstance(value.get("State"), dict) and
                value.get("Name") == "/" + expected["container_name"] and value.get("Image") == expected["image"] and
                all((config.get("Labels") or {}).get(key) == item for key, item in expected["labels"].items()) and
                (state["container_id"] is None or state["container_id"] == value["Id"]),
                "recovery_required", "Service identity differs from this preparation; foreign work will not be adopted or stopped")
        return value

    def verify_service(self, plan, component, value, *, running=False):
        state = self.states[(plan["artifact_id"], component)]
        expected = service_config(state["document"])
        service = next(item for item in plan["services"] if "service:" + item["id"] == component)
        limits = service["resources"]
        config, host, status = value.get("Config", {}), value.get("HostConfig", {}), value.get("State", {})
        image = self.images[service["image"]]
        require(isinstance(host, dict), "invalid_runtime", "Malformed service configuration")
        require(isinstance(config.get("Healthcheck"), dict) and isinstance(host.get("RestartPolicy"), dict),
                "invalid_runtime", "Malformed service health/restart configuration")
        require(config.get("User") == service["user"] and config.get("Healthcheck", {}).get("Test") == ["NONE"] and
                all(config.get(key) == image.get(key) for key in ("Env", "Entrypoint", "Cmd", "WorkingDir")) and
                status.get("Running") is running and status.get("Paused") is False and status.get("Restarting") is False and status.get("Dead") is False and
                host.get("Init") is True and host.get("ReadonlyRootfs") is True and host.get("Privileged") is False and
                not host.get("CapAdd") and host.get("CapDrop") == ["ALL"] and host.get("SecurityOpt") in (["no-new-privileges"], ["no-new-privileges:true"]) and
                all(not host.get(key) for key in ("PortBindings", "Devices", "DeviceRequests", "ExtraHosts", "PidMode", "UTSMode", "UsernsMode", "VolumesFrom")) and
                host.get("IpcMode") == "private" and host.get("RestartPolicy", {}).get("Name") == "no" and
                host.get("Memory") == limits["memory_mb"] * 1048576 and host.get("MemorySwap") == limits["memory_mb"] * 1048576 and
                host.get("PidsLimit") == limits["pids"] and host.get("NanoCpus") == int(limits["cpus"] * 10**9) and
                host.get("StorageOpt") == expected["storage_opt"] and
                host.get("LogConfig") == {"Type": "local", "Config": expected["logging"]["options"]} and
                host.get("Tmpfs", {}) == dict(item.split(":", 1) for item in expected["tmpfs"]) and
                host.get("Dns") == ["127.0.0.1"] and host.get("DnsSearch") == ["."] and host.get("DnsOptions") == ["ndots:0"],
                "invalid_runtime", "Effective service settings differ from approved limits/isolation")
        mounts = value.get("Mounts")
        require(isinstance(mounts, list) and all(isinstance(item, dict) for item in mounts) and
                len(mounts) == len(expected["volumes"]) + len(expected["tmpfs"]), "invalid_runtime", "Unexpected service mounts")
        actual = {item.get("Destination"): item for item in mounts}
        require(len(actual) == len(mounts), "invalid_runtime", "Duplicate service mount destinations")
        for volume in expected["volumes"]:
            item = actual.get(volume["target"], {})
            require(item.get("Type") == "bind" and item.get("Source") == volume["source"] and item.get("RW") is False and
                    item.get("Propagation") == "rprivate", "invalid_runtime", "Credential mount is not scoped/read-only")
        for tmpfs in service["tmpfs"]:
            item = actual.get(tmpfs["target"], {})
            require(item.get("Type") == "tmpfs" and item.get("RW") is True, "invalid_runtime", "Service tmpfs differs from approved storage")
        network = state["attachments"][0]
        endpoints = value.get("NetworkSettings", {}).get("Networks")
        require(isinstance(endpoints, dict) and set(endpoints) == {network["name"]} and
                host.get("NetworkMode") in (network["name"], network["network_id"]), "invalid_runtime", "Unexpected service networks")
        endpoint = endpoints[network["name"]]
        require(isinstance(endpoint, dict) and endpoint.get("NetworkID") == network["network_id"] and
                endpoint.get("IPAddress") == network["ipv4_address"] and not endpoint.get("GlobalIPv6Address") and
                isinstance(endpoint.get("Aliases"), list) and all(isinstance(alias, str) for alias in endpoint["Aliases"]) and
                service_identity(component) in endpoint["Aliases"] and
                set(endpoint["Aliases"]) <= {service_identity(component), expected["container_name"], value["Id"], value["Id"][:12]},
                "invalid_runtime", "Service attachment identity differs from assigned endpoint")

    def wait_ready(self, plan, component, timeout):
        self.require_plan(plan)
        require(component in plan["components"], "invalid_runtime", "Unknown readiness component")
        remaining = self.budget(timeout)
        if component == "proxy":
            self.network.wait_proxy_ready(plan, remaining())
        else:
            service = next((item for item in plan["services"] if "service:" + item["id"] == component), None)
            require(service is not None, "invalid_runtime", "Unknown readiness component")
            remaining = self.budget(min(remaining(), service["readiness"]["timeout_seconds"], service["resources"]["command_seconds"]))
            value = self.owned(plan, component, remaining())
            self.verify_service(plan, component, value, running=True)
            # Trusted Docker only on host; approved readiness argv runs in container.
            # On timeout the controller must stop the container: killing the CLI
            # alone does not prove cancellation of the container-local exec child.
            self.docker.docker(["exec", value["Id"], *service["readiness"]["argv"]],
                               min(remaining(), service["readiness"]["timeout_seconds"]), max_bytes=65536)
            remaining()
            latest = self.owned(plan, component, remaining())
            self.verify_service(plan, component, latest, running=True)
            self.network.verify_component(plan, component, latest, remaining())
        remaining()

    def stop_components(self, plan, components, timeout):
        remaining = self.budget(timeout)
        confirmed = True
        for component in components:
            try:
                self.require_plan(plan)
                require(component in plan["components"], "invalid_runtime", "Unknown stop component")
                if component == "proxy":
                    confirmed = self.network.stop_proxy(plan, remaining()) is True and confirmed
                    remaining()
                    continue
                value = self.owned(plan, component, remaining())
                state = self.states[(plan["artifact_id"], component)]
                # An ambiguous create is reconciled for stopping only with the
                # recorded nonce; never reuse it for dispatch/readiness.
                state["container_id"] = value["Id"]
                try:
                    self.checkpoint(plan, component, "stop-intent", {"container_id": value["Id"]})
                except (RoutineError, OSError):
                    confirmed = False
                if value["State"].get("Running") is not False:
                    self.docker.docker(["stop", "--time", "5", value["Id"]], remaining())
                latest = self.owned(plan, component, remaining())
                require(latest["State"].get("Running") is False and latest["State"].get("Paused") is False and
                        latest["State"].get("Restarting") is False, "stop_unconfirmed", "Service stopping is not confirmed")
                remaining()
                self.checkpoint(plan, component, "stopped", {"container_id": value["Id"]})
            except (RoutineError, OSError):
                confirmed = False
        # Retain containers, networks, manifests and credential files. The lifecycle
        # controller owns cleanup of delivery files after this literal True result.
        return confirmed
