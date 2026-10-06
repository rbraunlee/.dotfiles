"""Container-only component probe; not a production baseline/storage fallback."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import time

if not Path("/.dockerenv").is_file() or os.geteuid() != 10001:
    raise SystemExit("Run this probe only in the bounded qualification container")

spec = importlib.util.spec_from_file_location("worker", "/opt/routine/bundle/worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
Path("/home/worker/project").mkdir()
fixture_bytes = b"Approved read-only input fixture.\n"
mount = {"source": "fixture.data", "target": "/inputs/fixture.data", "sha256": worker.sha(fixture_bytes), "read_only": True}
context = {"deadline_epoch": time.time() + 90, "request": {"run_id": "component-qualification"},
           "profile": {"mounts": [mount], "resources": {"disk_mb": 1}},
           "mounts": [{key: mount[key] for key in ("source", "target", "sha256")} | {"size_bytes": len(fixture_bytes)}]}
baseline = worker.Baseline(context)
server = None
result = {"test": "read-only-bounded-service-component", "passed": False, "mounts": []}
log = Path("/home/worker/service.log").open("wb")
try:
    worker.verify_mounts(context, baseline, result["mounts"])
    server = subprocess.Popen(["/usr/local/bin/opencode", "serve", "--hostname", "127.0.0.1", "--port", "4096"],
                              cwd="/control", stdout=log, stderr=log, start_new_session=True)
    while True:
        baseline.remaining()
        if server.poll() is not None:
            raise worker.WorkerFailure("service_start_failed")
        baseline.password = worker.service_password("/home/worker/service.log")
        if baseline.password is None:
            time.sleep(0.1)
            continue
        try:
            info = baseline.api("get", "/api/info")
            break
        except (worker.WorkerFailure, ValueError):
            time.sleep(0.1)
    assert info["version"] == "2.0.22"
    assert info["pid"] == server.pid
    command = "\n".join([
        "import os,pathlib,socket",
        "assert os.geteuid()==10001",
        "assert set(os.listdir('/sys/class/net')) == {'lo'}",
        "assert not pathlib.Path('/var/run/docker.sock').exists()",
        "assert not pathlib.Path(os.environ['ROUTINE_COMPONENT_HOST_CANARY']).exists()",
        "for filename in ('ledger.json','ledger.lock'):",
        "    host_file=pathlib.Path(os.environ['ROUTINE_COMPONENT_HOST_STATE'])/filename",
        "    assert not host_file.exists()",
        "    for access in (os.O_RDONLY,os.O_WRONLY):",
        "        try:",
        "            descriptor=os.open(host_file,access)",
        "        except OSError:",
        "            continue",
        "        os.close(descriptor)",
        "        raise AssertionError('Host ledger/lock was accessible')",
        "assert not os.access('/control',os.W_OK)",
        "assert not os.access('/opt/routine/config',os.W_OK)",
        "assert os.statvfs('/').f_flag & os.ST_RDONLY",
        "assert os.statvfs('/home/worker').f_blocks*os.statvfs('/home/worker').f_frsize == 384*1024**2",
        "assert os.statvfs('/tmp').f_blocks*os.statvfs('/tmp').f_frsize == 32*1024**2",
        "assert pathlib.Path('/sys/fs/cgroup/memory.max').read_text().strip() == str(768*1024**2)",
        "assert pathlib.Path('/sys/fs/cgroup/pids.max').read_text().strip() == '64'",
        "assert pathlib.Path('/inputs/fixture.data').read_bytes() == b'Approved read-only input fixture.\\n'",
        "assert os.statvfs('/inputs/fixture.data').f_flag & os.ST_RDONLY",
        "try:",
        "    pathlib.Path('/inputs/fixture.data').write_text('unapproved edit')",
        "except OSError:",
        "    pass",
        "else:",
        "    raise AssertionError('Input snapshot was writable')",
        "for address in [('172.17.0.1',80),('192.168.1.1',80),('1.1.1.1',443)]:",
        "    try:",
        "        connection=socket.create_connection(address,timeout=0.2)",
        "    except OSError:",
        "        continue",
        "    connection.close()",
        "    raise AssertionError('Unexpected outbound access')",
        "try:",
        "    connection=socket.socket(socket.AF_INET6,socket.SOCK_STREAM)",
        "    connection.settimeout(0.2)",
        "    connection.connect(('2606:4700:4700::1111',443))",
        "except OSError:",
        "    pass",
        "else:",
        "    raise AssertionError('Unexpected IPv6 outbound access')",
        "finally:",
        "    connection.close()",
        "pathlib.Path('service-tool-locality-canary').write_text(socket.gethostname())",
        "print('qualification-secret-canary-DO-NOT-EXPORT')",
    ])
    check = baseline.command("isolation", "check", {"argv": ["python3", "-c", command], "timeout_seconds": 30})
    assert check["status"] == "exited" and check["exit"] == 0
    assert Path("/home/worker/project/service-tool-locality-canary").is_file()
    child_script = ("import os,pathlib,time; "
                    "pathlib.Path('timeout-child.pid').write_text(str(os.getpid())); "
                    "time.sleep(4); pathlib.Path('timeout-descendant-survived').write_text('unsafe')")
    setup_script = ("import pathlib,subprocess,sys,time; "
                    f"subprocess.Popen([sys.executable,'-B','-c',{child_script!r}]); "
                    "time.sleep(30)")
    started = time.monotonic()
    timed_out = baseline.command("timeout-setup", "setup", {"argv": ["python3", "-c", setup_script], "timeout_seconds": 1})
    elapsed = time.monotonic() - started
    assert (timed_out["status"], timed_out["exit"]) != ("exited", 0)
    assert elapsed < 6
    cleanup_script = "\n".join([
        "import pathlib,time",
        "pid=int(pathlib.Path('timeout-child.pid').read_text())",
        "status=pathlib.Path(f'/proc/{pid}/stat')",
        "time.sleep(4)",
        "assert not pathlib.Path('timeout-descendant-survived').exists()",
        "assert not status.exists() or status.read_text().split(') ',1)[1].split()[0]=='Z'",
    ])
    cleanup = baseline.command("timeout-cleanup", "check", {"argv": ["python3", "-c", cleanup_script], "timeout_seconds": 10})
    assert cleanup["status"] == "exited" and cleanup["exit"] == 0
    result.update(passed=True, service={"version": info["version"], "pid": info["pid"], "uid": os.geteuid()}, check=check,
                  setup_timeout=timed_out, setup_timeout_seconds=elapsed, timeout_cleanup=cleanup,
                  storage="read-only root; bounded RAM-backed test directories only; not production baseline admission")
except Exception as error:
    result["diagnostic"] = str(error) if isinstance(error, worker.WorkerFailure) else type(error).__name__
finally:
    if server is not None and server.poll() is None:
        os.killpg(server.pid, signal.SIGTERM)
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(server.pid, signal.SIGKILL)
            server.wait()
    log.close()
print(json.dumps(result, sort_keys=True))
raise SystemExit(0 if result["passed"] else 1)
