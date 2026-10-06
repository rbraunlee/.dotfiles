"""Explicitly opted-in resource exhaustion; never relax production disk admission."""
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
from routine.process import host_environment, run_bounded


@unittest.skipUnless(os.environ.get("OPENCODE_ROUTINE_COMPONENT_IMAGE"),
                     "Resource tests require an explicitly approved pinned image and Docker access")
class ResourceQualification(unittest.TestCase):
    def qualify(self, mode):
        image = os.environ["OPENCODE_ROUTINE_COMPONENT_IMAGE"]
        self.assertRegex(image, r"^sha256:[0-9a-f]{64}$")
        docker = ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"]
        images = json.loads(run_bounded(docker + ["image", "inspect", image], timeout=15))
        self.assertEqual(images[0]["Id"], image)
        self.assertEqual(images[0]["Config"]["Labels"]["routine.bundle-sha256"], bundle_identity())
        root = Path(tempfile.mkdtemp(prefix="routine-m2-resources-", dir="/tmp/opencode"))
        script = (PACKAGE / "tests/fixtures/resource_component.py").read_text()
        name = "routine-resource-" + mode + "-" + uuid.uuid4().hex[:12]
        command = docker + ["run", "--detach", "--pull", "never", "--name", name, "--read-only", "--network", "none",
                            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--user", "10001:10001",
                            "--memory", "96m", "--memory-swap", "96m", "--cpus", "0.25", "--pids-limit", "32",
                            "--log-driver", "local", "--log-opt", "max-size=1m", "--log-opt", "max-file=1",
                            "--log-opt", "compress=false", "--tmpfs", "/tmp:rw,size=8m,mode=1777",
                            "--entrypoint", "python3", image, "-B", "-c", script, mode]
        record = {"test": mode, "image_id": image, "bundle_sha256": bundle_identity(), "container": name,
                  "probe_sha256": digest(script.encode()), "production_baseline_admitted": False}
        output = b""
        try:
            run_bounded(command, timeout=20)
            record["exit_code"] = int(run_bounded(docker + ["wait", name], timeout=40).strip())
            output = run_bounded(docker + ["logs", name], timeout=15, max_bytes=1024 * 1024 + 128 * 1024)
            record.update(output_bytes=len(output), output_sha256=digest(output))
            record["result"] = json.loads(output.splitlines()[-1])
        finally:
            # Stop and retain only the specifically named disposable container.
            subprocess.run(docker + ["stop", "--time", "5", name], env=host_environment(),
                           capture_output=True, text=True, timeout=15)
            inspection = subprocess.run(docker + ["inspect", name], env=host_environment(),
                                        capture_output=True, text=True, timeout=15)
            if inspection.returncode == 0:
                (root / "container-inspect.json").write_text(inspection.stdout)
                record["container_stopped"] = not json.loads(inspection.stdout)[0]["State"]["Running"]
            (root / "qualification.json").write_text(json.dumps(record, indent=2) + "\n")
            print(f"Resource evidence retained: {root}")
        self.assertEqual(record["exit_code"], 0, record)
        self.assertTrue(record.get("container_stopped"))
        self.assertTrue(record["result"]["passed"], record)
        return record, output

    def test_pid_limit_rejects_finite_process_creation(self):
        record, _ = self.qualify("pids")
        self.assertTrue(record["result"]["observed"]["denied"])

    def test_memory_limit_kills_bounded_allocation_child(self):
        record, _ = self.qualify("memory")
        self.assertGreater(record["result"]["observed"]["oom_kills"], 0)

    def test_cpu_limit_actually_throttles(self):
        record, _ = self.qualify("cpu")
        self.assertGreater(record["result"]["observed"]["throttled_periods"], 0)

    def test_component_tmpfs_limit_rejects_bounded_fill(self):
        record, _ = self.qualify("tmpfs")
        self.assertFalse(record["result"]["observed"]["production_writable_layer_qualified"])

    def test_docker_log_rotation_drops_early_output_and_preserves_tail(self):
        record, output = self.qualify("logs")
        self.assertGreater(record["result"]["observed"]["lines_emitted"] * 1024, len(output))
        self.assertNotIn(b"routine-log-0000 ", output)
        self.assertIn(b"routine-log-4095 ", output)


if __name__ == "__main__":
    unittest.main()
