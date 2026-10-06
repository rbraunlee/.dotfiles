"""Immutable-ID proxy create/inspect/bootstrap/start/health/stop transactions."""
import os
from pathlib import Path
import stat

from .contracts import canonical, hash_value, require
from .network_transport import Budget, fingerprint
from .proxy import proxy_healthcheck, retained_file, sync_directory


def healthcheck(policy_hash, bundle_hash):
    # The existing offline health script already verifies policy bytes/read-only
    # status, bundle assets, UID and invalid HTTP denial on loopback. Networking
    # mode cannot require only lo; interface isolation is independently verified.
    test = proxy_healthcheck(policy_hash, bundle_hash)
    test[5] = test[5].replace(" assert set(os.listdir('/sys/class/net'))=={'lo'}\n", "")
    return test


def proxy_create(plan, attachments, policy_path, preparation_id):
    limits, artifact = plan["resources"], plan["artifact_id"]
    policy_hash = fingerprint(plan["proxy_policy"])
    hash_value(plan["bundle_sha256"])
    return {"Image": plan["runtime"]["image"], "User": "10001:10001", "WorkingDir": "/control",
            "Entrypoint": ["python3", "-I", "-B", "/opt/routine/bundle/proxy.py", "/policy/proxy.json"],
            "Cmd": [], "Env": [], "ExposedPorts": {},
            "Labels": {"routine.artifact-id": artifact, "routine.component": "proxy", "routine.launch-id": preparation_id,
                       "routine.proxy-policy-sha256": policy_hash, "routine.proxy-mode": "gated-network-check"},
            "Healthcheck": {"Test": healthcheck(policy_hash, plan["bundle_sha256"]), "Interval": 1000000000,
                            "Timeout": 1000000000, "Retries": 1},
            "HostConfig": {"NetworkMode": attachments[0]["network_id"], "ReadonlyRootfs": True, "Privileged": False,
                           "PublishAllPorts": False, "PortBindings": {}, "CapAdd": [], "CapDrop": ["ALL"],
                           "SecurityOpt": ["no-new-privileges:true"], "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0},
                           "Init": True, "Devices": [], "ExtraHosts": [], "PidMode": "", "IpcMode": "private",
                           "Memory": limits["memory_mb"] * 1048576, "MemorySwap": limits["memory_mb"] * 1048576,
                           "PidsLimit": limits["pids"], "NanoCpus": int(limits["cpus"] * 1000000000),
                           "LogConfig": {"Type": "local", "Config": {"max-size": str(limits["log_mb"]) + "m", "max-file": "1", "compress": "false"}},
                           "Mounts": [{"Type": "bind", "Source": str(policy_path), "Target": "/policy/proxy.json", "ReadOnly": True,
                                       "BindOptions": {"NonRecursive": True}}]},
            "NetworkingConfig": {"EndpointsConfig": {entry["name"]: {"IPAMConfig": {"IPv4Address": entry["ipv4_address"]},
                                    "NetworkID": entry["network_id"], "Aliases": []} for entry in attachments}}}


class ProxyLifecycle:
    def __init__(self, adapter, artifact_root):
        self.adapter, self.artifact_root = adapter, artifact_root

    def _policy(self, plan):
        require(self.artifact_root is not None, "policy_unavailable", "A private trusted artifact directory is required")
        root = Path(self.artifact_root).absolute()
        for path in [root] + list(root.parents):
            info = path.lstat()
            require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode), "unsafe_state", "Unsafe proxy artifact ancestry")
        info = root.stat()
        require(info.st_uid == os.getuid() and info.st_mode & 0o077 == 0, "unsafe_state", "Proxy artifact root must be private and owned")
        directory = root / ("network-" + plan["artifact_id"])
        directory.mkdir(mode=0o700)  # Never reuse interrupted/retained artifacts.
        path = directory / "proxy.json"
        data = canonical(plan["proxy_policy"])
        require(len(data) <= 65536, "input_limit", "Proxy policy exceeds its bound")
        retained_file(path, data, 0o444)
        sync_directory(directory)
        sync_directory(root)
        return path

    def start(self, plan, timeout):
        adapter, budget = self.adapter, Budget(timeout, self.adapter.clock)
        record = adapter._record(plan)
        require("proxy" in plan["components"] and "proxy" not in record and not record.get("failed_components"),
                "recovery_required", "Proxy is absent, held or already attempted")
        attachments = adapter.component_networks(plan, "proxy")
        name = "routine-network-proxy-" + plan["artifact_id"][:32]
        from urllib.parse import urlencode
        rows = adapter._docker(budget, "GET", "/containers/json?" + urlencode({"all": "true", "filters": canonical({"name": ["^/" + name + "$"]}).decode()}))
        require(rows == [], "recovery_required", "An existing proxy cannot be adopted or replaced")
        path = self._policy(plan)
        body = proxy_create(plan, attachments, path, record["nonce"])
        image = adapter._docker(budget, "GET", "/images/" + plan["runtime"]["image"] + "/json")
        require(isinstance(image, dict) and image.get("Id") == plan["runtime"]["image"] and
                image.get("Config", {}).get("Labels", {}).get("routine.bundle-sha256") == plan["bundle_sha256"] and
                image.get("Config", {}).get("Labels", {}).get("routine.opencode-version") == plan["runtime"]["opencode_version"],
                "invalid_runtime", "Proxy local image/bundle/release identity mismatch")
        adapter._event(record, "proxy-create-intent", name=name, transaction=body, policy_sha256=fingerprint(plan["proxy_policy"]))
        proxy = {"body": body, "name": name, "path": path, "container_id": None, "attempted": True}
        policy_stat = path.lstat()
        proxy["policy_inode"] = (policy_stat.st_dev, policy_stat.st_ino)
        record["proxy"] = proxy
        created = adapter._docker(budget, "POST", "/containers/create?" + urlencode({"name": name}), body)
        require(isinstance(created, dict) and not created.get("Warnings"), "recovery_required", "Ambiguous proxy creation")
        container_id = created.get("Id")
        hash_value(container_id)
        proxy["container_id"] = container_id
        # Identity intent is durable before bootstrap/start. Callback failure does
        # not discard the local ID, permitting only a verified bounded stop.
        adapter._event(record, "proxy-created", container_id=container_id)
        value = self._inspect(record, budget)
        require(value.get("State", {}).get("Running") is False, "recovery_required", "Proxy unexpectedly running before enforcement")
        adapter.verify_component(plan, "proxy", value, budget.remaining())
        budget.remaining()
        adapter._event(record, "proxy-start-intent", container_id=container_id)
        adapter._docker(budget, "POST", "/containers/" + container_id + "/start")

    def _inspect(self, record, budget):
        adapter, proxy = self.adapter, record.get("proxy")
        require(proxy is not None and proxy["container_id"] is not None, "recovery_required", "Proxy creation identity is unknown")
        value = adapter._docker(budget, "GET", "/containers/" + proxy["container_id"] + "/json")
        body = proxy["body"]
        require(isinstance(value, dict) and value.get("Id") == proxy["container_id"] and value.get("Name") == "/" + proxy["name"] and
                value.get("Image") == body["Image"] and isinstance(value.get("State"), dict),
                "recovery_required", "Proxy immutable identity changed")
        config, host = value.get("Config", {}), value.get("HostConfig", {})
        require(isinstance(config, dict) and isinstance(host, dict), "invalid_runtime", "Malformed proxy configuration sections")
        require(all(config.get(key) == body[key] for key in ("User", "WorkingDir", "Entrypoint", "Cmd", "Env", "Labels", "Healthcheck")) and
                all(host.get(key) == expected for key, expected in body["HostConfig"].items() if key != "Mounts") and
                not host.get("Binds") and not host.get("VolumesFrom") and not host.get("Tmpfs") and not config.get("Volumes"),
                "invalid_runtime", "Effective proxy configuration differs from its immutable transaction")
        mounts = value.get("Mounts")
        require(isinstance(mounts, list) and len(mounts) == 1 and mounts[0].get("Type") == "bind" and
                mounts[0].get("Source") == str(proxy["path"]) and mounts[0].get("Destination") == "/policy/proxy.json" and
                mounts[0].get("RW") is False and fingerprint(record["plan"]["proxy_policy"]) ==
                config["Labels"]["routine.proxy-policy-sha256"], "invalid_runtime", "Proxy policy mount changed")
        fd = os.open(proxy["path"], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as stream:
            observed = os.fstat(stream.fileno())
            require(stat.S_ISREG(observed.st_mode) and observed.st_nlink == 1 and observed.st_uid == os.getuid() and
                    observed.st_mode & 0o777 == 0o444 and (observed.st_dev, observed.st_ino) == proxy["policy_inode"] and
                    stream.read(65537) == canonical(record["plan"]["proxy_policy"]),
                    "unsafe_state", "Retained proxy policy inode, bytes or permissions changed")
        adapter._component_identity(record["plan"], "proxy", value)
        return value

    def ready(self, plan, timeout):
        adapter, budget, record = self.adapter, Budget(timeout, self.adapter.clock), self.adapter._record(plan)
        while True:
            value = self._inspect(record, budget)
            status = value["State"].get("Health", {}).get("Status")
            require(value["State"].get("Running") is True and status in ("starting", "healthy"),
                    "adapter_failed", "Proxy listener/policy readiness is not confirmed")
            if status == "healthy":
                break
            adapter.sleep(min(0.1, budget.remaining()))
            budget.remaining()
        adapter.verify_component(plan, "proxy", value, budget.remaining())
        budget.remaining()
        adapter._event(record, "proxy-ready", container_id=value["Id"], qualified=False, egress_qualified=False)

    def stop(self, plan, timeout):
        adapter, budget, record = self.adapter, Budget(timeout, self.adapter.clock), self.adapter._record(plan)
        # Unknown creation or replaced identity is held, never addressed by name.
        value = self._inspect(record, budget)
        adapter._event(record, "proxy-stop-intent", container_id=value["Id"])
        adapter._docker(budget, "POST", "/containers/" + value["Id"] + "/stop?t=5")
        value = self._inspect(record, budget)
        require(value["State"].get("Running") is False and value["State"].get("Paused") is False and
                value["State"].get("Restarting") is False, "stop_unconfirmed", "Proxy stopping is not confirmed")
        adapter._event(record, "proxy-stopped", container_id=value["Id"], retained=True)
        budget.remaining()
        return True
