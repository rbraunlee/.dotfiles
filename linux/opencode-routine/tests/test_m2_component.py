"""Opt-in component qualification with bounded RAM, independent of disk admission."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

from test_m1 import PACKAGE
from routine.compose import bundle_identity
from routine.contracts import digest
from routine.process import host_environment
from routine.store import Store


class ComponentQualification(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("OPENCODE_ROUTINE_COMPONENT_IMAGE"),
                         "Component test requires an explicitly approved pinned image and Docker access")
    def test_container_local_service_on_read_only_root_and_bounded_ram(self):
        image = os.environ["OPENCODE_ROUTINE_COMPONENT_IMAGE"]
        self.assertRegex(image, r"^sha256:[0-9a-f]{64}$")
        root = Path(tempfile.mkdtemp(prefix="routine-m2-component-", dir="/tmp/opencode"))
        canary = root / "host-only-canary"
        canary.write_text("This fixture must not be visible inside the container.\n")
        state = Store(root / "host-state")
        state.write({"version": 1, "features": {}, "runs": {}})
        with state.lock("ledger.lock"):
            pass
        state_files = [state.root / "ledger.json", state.root / "ledger.lock"]
        state_before = {path.name: digest(path.read_bytes()) for path in state_files}
        handoff = root / "handoff"
        (handoff / "mounts").mkdir(parents=True, mode=0o755)
        snapshot = handoff / "mounts/0001.bin"
        snapshot.write_bytes(b"Approved read-only input fixture.\n")
        snapshot.chmod(0o444)
        (handoff / "mounts").chmod(0o555)
        handoff.chmod(0o555)
        name = "routine-component-" + uuid.uuid4().hex[:12]
        docker = ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"]
        environment = host_environment()
        images = json.loads(subprocess.check_output(docker + ["image", "inspect", image], env=environment, timeout=15))
        self.assertEqual(images[0]["Id"], image)
        self.assertEqual(images[0]["Config"]["Labels"]["routine.bundle-sha256"], bundle_identity())
        script = (PACKAGE / "tests/fixtures/service_component.py").read_text()
        command = docker + ["run", "--pull", "never", "--name", name, "--read-only", "--network", "none",
                            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--user", "10001:10001",
                            "--memory", "768m", "--memory-swap", "768m", "--cpus", "1", "--pids-limit", "64",
                            "--log-driver", "local", "--log-opt", "max-size=1m", "--log-opt", "max-file=1",
                            "--log-opt", "compress=false", "--tmpfs", "/home/worker:rw,size=384m,uid=10001,gid=10001,mode=0700",
                            "--tmpfs", "/tmp:rw,size=32m,mode=1777",
                            "--mount", f"type=bind,source={handoff},target=/handoff,readonly",
                            "--mount", f"type=bind,source={snapshot},target=/inputs/fixture.data,readonly"]
        for key, value in {"HOME": "/home/worker", "XDG_CONFIG_HOME": "/opt/routine/config",
                           "XDG_STATE_HOME": "/home/worker/.state", "XDG_DATA_HOME": "/home/worker/.data",
                            "XDG_CACHE_HOME": "/home/worker/.cache", "PYTHONDONTWRITEBYTECODE": "1",
                            "ROUTINE_COMPONENT_HOST_CANARY": str(canary),
                            "ROUTINE_COMPONENT_HOST_STATE": str(state.root)}.items():
            command += ["--env", key + "=" + value]
        command += ["--entrypoint", "python3", image, "-B", "-c", script]
        record = {"image_id": image, "bundle_sha256": bundle_identity(), "container": name,
                  "probe_sha256": digest(script.encode()), "production_baseline_admitted": False}
        try:
            completed = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=110)
            record.update(returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
        except subprocess.TimeoutExpired:
            record["diagnostic"] = "host_test_timeout"
        finally:
            # Stop only this test's named container; retain it and the test evidence.
            subprocess.run(docker + ["stop", "--time", "5", name], env=environment,
                           capture_output=True, text=True, timeout=15)
            inspection = subprocess.run(docker + ["inspect", name], env=environment,
                                        capture_output=True, text=True, timeout=15)
            if inspection.returncode == 0:
                (root / "container-inspect.json").write_text(inspection.stdout)
                record["container_stopped"] = not json.loads(inspection.stdout)[0]["State"]["Running"]
            record["host_state_unchanged"] = state_before == {path.name: digest(path.read_bytes()) for path in state_files}
            (root / "qualification.json").write_text(json.dumps(record, indent=2) + "\n")
            print(f"Component evidence retained: {root}")
        self.assertEqual(record.get("returncode"), 0, record)
        self.assertTrue(record.get("container_stopped"))
        self.assertTrue(record["host_state_unchanged"])
        result = json.loads(record["stdout"])
        self.assertTrue(result["passed"])
        self.assertEqual(result["mounts"], [{"source": "fixture.data", "target": "/inputs/fixture.data",
                                           "sha256": digest(snapshot.read_bytes()), "size_bytes": snapshot.stat().st_size}])
        self.assertEqual(result["service"]["version"], "2.0.22")
        self.assertEqual(result["check"]["output_sha256"], digest(b"qualification-secret-canary-DO-NOT-EXPORT\n"))
        self.assertNotIn("qualification-secret-canary-DO-NOT-EXPORT", record["stdout"])
        self.assertNotEqual((result["setup_timeout"]["status"], result["setup_timeout"]["exit"]), ("exited", 0))
        self.assertLess(result["setup_timeout_seconds"], 6)
        self.assertEqual(result["timeout_cleanup"]["exit"], 0)


if __name__ == "__main__":
    unittest.main()
