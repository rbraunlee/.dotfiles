"""Run-scoped offline proxy checks. No network/firewall or egress admission."""
import os
from pathlib import Path
import time

from .contracts import RoutineError, canonical, digest, hash_value, identifier, load_package, require, validate_profile
from .launcher import now


TERMINAL = ("proxy-check-passed", "proxy-check-failed")
POLICY_LIMIT = 65536


def proxy_policy(profile):
    validate_profile(profile)
    require(profile["version"] == 2, "runtime_missing", "Proxy checks require a pinned profile v2 runtime")
    require("proxy" in profile["network"], "proxy_policy_missing", "Explicit approved proxy limits are required")
    policy = {"allowed_domains": list(profile["network"]["allowed_domains"]), **profile["network"]["proxy"]}
    require(len(canonical(policy)) <= POLICY_LIMIT, "input_limit", "Proxy policy exceeds the component input limit")
    return policy


def proxy_healthcheck(policy_sha256, bundle_sha256):
    hash_value(policy_sha256)
    hash_value(bundle_sha256)
    # Only loopback, no DNS or upstream connection. No exception/request output is
    # written to Docker health logs. Check actual policy/asset bytes and read denial
    # before treating the listener as ready. This is NOT approved-egress evidence.
    script = "\n".join([
        "import hashlib,json,os,pathlib,socket,sys",
        "try:",
        " p=pathlib.Path('/policy/proxy.json')",
        " data=p.read_bytes()",
        " assert len(data)<=65536 and hashlib.sha256(data).hexdigest()==sys.argv[1]",
        " assert os.geteuid()==10001 and os.statvfs(p).f_flag & os.ST_RDONLY",
        " assert set(os.listdir('/sys/class/net'))=={'lo'}",
        " root=pathlib.Path('/opt/routine/bundle')",
        " assets={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ('Dockerfile','worker.py','opencode.json','proxy.py')}",
        " assert hashlib.sha256(json.dumps(assets,sort_keys=True,separators=(',',':')).encode()).hexdigest()==sys.argv[2]",
        " sys.path.insert(0,str(root))",
        " from proxy import Proxy",
        " Proxy(**json.loads(data))",
        " with socket.create_connection(('127.0.0.1',3128),timeout=0.5) as s:",
        "  s.sendall(b'GET / HTTP/1.1\\r\\nHost: denied.invalid\\r\\n\\r\\n')",
        "  assert s.recv(256).startswith(b'HTTP/1.1 403 Forbidden\\r\\n')",
        "except Exception:",
        " sys.exit(1)",
    ])
    return ["CMD", "python3", "-I", "-B", "-c", script, policy_sha256, bundle_sha256]


def proxy_document(profile, policy_path, artifact_id, policy_sha256, bundle_sha256=None):
    from .compose import bundle_identity

    proxy_policy(profile)
    hash_value(artifact_id)
    hash_value(policy_sha256)
    bundle_sha256 = bundle_sha256 or bundle_identity()
    limits = profile["resources"]
    return {"services": {"proxy": {
        "image": profile["runtime"]["image"], "pull_policy": "never",
        "container_name": "routine-proxy-" + artifact_id[:32],
        "entrypoint": ["python3", "-I", "-B", "/opt/routine/bundle/proxy.py", "/policy/proxy.json"],
        "user": "10001:10001", "working_dir": "/control", "init": True,
        "network_mode": "none", "read_only": True, "restart": "no", "privileged": False,
        "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
        "cpus": limits["cpus"], "mem_limit": f"{limits['memory_mb']}m",
        "memswap_limit": f"{limits['memory_mb']}m", "pids_limit": limits["pids"],
        "logging": {"driver": "local", "options": {"max-size": f"{limits['log_mb']}m", "max-file": "1", "compress": "false"}},
        "volumes": [{"type": "bind", "source": str(policy_path), "target": "/policy/proxy.json", "read_only": True,
                     "bind": {"create_host_path": False}}],
        "labels": {"routine.artifact-id": artifact_id, "routine.proxy-policy-sha256": policy_sha256,
                   "routine.proxy-mode": "offline-check"},
        "healthcheck": {"test": proxy_healthcheck(policy_sha256, bundle_sha256),
                        "interval": "1s", "timeout": "1s", "retries": 1},
    }}}


def retained_file(path, data, mode):
    """Exclusive creation; sync retained identities before the creation boundary."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fchmod(stream.fileno(), mode)
        os.fsync(stream.fileno())


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class ProxyCheck:
    def __init__(self, adapter=None, clock=time.time):
        from .compose import DockerCompose

        self.adapter = adapter or DockerCompose()
        self.clock = clock

    @staticmethod
    def update(session, run_key, **values):
        store = session.launcher.store
        with store.lock("ledger.lock"):
            ledger = store.read()
            run = ledger["runs"][run_key]
            run["proxy"].update(values)
            store.write(ledger)
            return run

    def launch(self, session, run_id):
        identifier(run_id)
        require(session.active, "inactive_coordinator", "Coordinator lease has ended")
        launcher, store = session.launcher, session.launcher.store
        key = launcher.key(session.project_id, session.feature_id)
        run_key = f"{session.project_id}/{run_id}"
        # Share the baseline lock: a proxy check and worker launch cannot overlap.
        lock_id = digest(run_key.encode())
        artifact_id = digest(("proxy:" + run_key).encode())
        with store.lock("sandbox-" + lock_id + ".lock", blocking=False):
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
                require("environment" not in run or run["environment"]["state"] in
                        ("planned", "environment-blocked", "environment-check-passed", "environment-check-failed"),
                        "recovery_required", "Interrupted/held environment requires deliberate recovery")
                if "proxy" in run:
                    require(run["proxy"]["state"] in TERMINAL, "recovery_required", "Interrupted/held proxy requires deliberate recovery")
                    return {"run": run, "existing": True}
                require(run["state"] == "claimed", "recovery_required", "Proxy check requires an unused claimed run")
                package = load_package(Path(feature["project_root"]), session.feature_id)
                require(package == feature["package"], "changed_input", "Approved inputs changed before proxy preparation")
                profile = package["profile"]
                policy_data = canonical(proxy_policy(profile))
                policy_sha256 = digest(policy_data)
                run.setdefault("preparation_started_at", now())
                run.setdefault("preparation_epoch", self.clock())
                deadline = min(run["preparation_epoch"] + run["budgets"]["slice_seconds"],
                               self.clock() + profile["resources"]["command_seconds"])
                require(deadline > self.clock(), "command_timeout", "Slice budget exhausted before proxy preparation")
                run["proxy"] = {"state": "preparing", "artifact_id": artifact_id,
                                "started_at": now(), "deadline_epoch": deadline,
                                "policy_sha256": policy_sha256, "runtime_image": profile["runtime"]["image"],
                                "bundle_sha256": run["bundle_sha256"], "profile_sha256": run["profile_sha256"]}
                store.write(ledger)

            def remaining():
                require(deadline > self.clock(), "command_timeout", "Proxy check deadline exhausted")
                return deadline - self.clock()

            directory = store.root / "artifacts" / artifact_id
            attempted, stopped, ready = False, True, False
            directory_created = False
            diagnostic, evidence_sha256 = None, None
            try:
                artifacts = directory.parent
                artifacts.mkdir(mode=0o700, exist_ok=True)
                store._private(artifacts, directory=True)
                directory.mkdir(mode=0o700)
                store._private(directory, directory=True)
                directory_created = True
                sync_directory(artifacts)
                policy_dir = directory / "policy"
                policy_dir.mkdir(mode=0o755)
                retained_file(policy_dir / "proxy.json", policy_data, 0o444)
                policy_dir.chmod(0o555)
                sync_directory(policy_dir)
                document = proxy_document(profile, policy_dir / "proxy.json", artifact_id, policy_sha256, run["bundle_sha256"])
                compose_data = canonical(document)
                require(len(policy_data) + len(compose_data) <= profile["resources"]["disk_mb"] * 1024 * 1024,
                        "input_limit", "Proxy preparation exceeds the approved disk budget")
                retained_file(directory / "compose.json", compose_data, 0o600)
                sync_directory(directory)
                self.update(session, run_key, compose_sha256=digest(compose_data))
                self.adapter.preflight_proxy(profile, run["bundle_sha256"], artifact_id, remaining())
                # Do not mark creation attempted if the preflight consumed the budget.
                remaining()
                self.update(session, run_key, state="starting")
                timeout = remaining()
                attempted, stopped = True, False
                self.adapter.start_proxy(directory, artifact_id, timeout)
                self.adapter.wait_proxy_ready(artifact_id, profile, policy_sha256, remaining())
                remaining()  # A late-observed healthy status cannot establish success.
                ready = True
                self.update(session, run_key, state="ready")
            except (RoutineError, OSError) as exc:
                diagnostic = exc.code if isinstance(exc, RoutineError) else "io_error"
            finally:
                if attempted:
                    try:
                        self.update(session, run_key, state="stopping")
                    except (RoutineError, OSError) as exc:
                        # Ledger failure must not prevent stopping a created proxy.
                        diagnostic = exc.code if isinstance(exc, RoutineError) else "io_error"
                    try:
                        # Separate bounded cleanup, including after the check deadline.
                        self.adapter.stop_proxy(directory, artifact_id, 20)
                        stopped = True
                    except (RoutineError, OSError):
                        stopped = False
            state = "proxy-check-passed" if ready and diagnostic is None else "proxy-check-failed"
            if diagnostic == "recovery_required":
                # Existing environment is not ours to stop or replace. Hold all
                # further dispatch, rather than claiming absence/stopping.
                stopped = False
                state = "proxy-held"
            if not stopped:
                state = "proxy-held"
                if diagnostic != "recovery_required":
                    diagnostic = "stop_unconfirmed"
            evidence = {"version": 1, "request": run["request"], "artifact_id": artifact_id,
                        "policy_sha256": policy_sha256, "profile_sha256": run["profile_sha256"],
                        "bundle_sha256": run["bundle_sha256"], "runtime_image": profile["runtime"]["image"],
                        "outcome": state, "diagnostic": diagnostic, "listener_ready": ready,
                        "creation_attempted": attempted, "container_stopped": stopped,
                        "egress_enabled": False, "approved_external_access_qualified": False,
                        "host_firewall_qualified": False}
            try:
                require(directory_created, "io_error", "Proxy artifact directory was not prepared")
                retained_file(directory / "evidence.json", canonical(evidence), 0o600)
                sync_directory(directory)
                evidence_sha256 = digest(canonical(evidence))
            except (RoutineError, OSError):
                if stopped:
                    state, diagnostic = "proxy-check-failed", "io_error"
            run = self.update(session, run_key, state=state, completed_at=now(),
                              result={"outcome": state, "diagnostic": diagnostic, "container_stopped": stopped,
                                      "egress_enabled": False, "evidence_sha256": evidence_sha256})
            return {"run": run, "existing": False}
