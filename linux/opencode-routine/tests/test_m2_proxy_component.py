"""Opt-in bounded offline proxy component; no host networking/firewall mutation."""
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


class ProxyQualification(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("OPENCODE_ROUTINE_COMPONENT_IMAGE"),
                         "Proxy component requires an explicitly approved pinned image and Docker access")
    def test_offline_container_proxy_transport_and_denials(self):
        image = os.environ["OPENCODE_ROUTINE_COMPONENT_IMAGE"]
        self.assertRegex(image, r"^sha256:[0-9a-f]{64}$")
        docker = ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"]
        images = json.loads(run_bounded(docker + ["image", "inspect", image], timeout=15))
        self.assertEqual(images[0]["Id"], image)
        self.assertEqual(images[0]["Config"]["Labels"]["routine.bundle-sha256"], bundle_identity())
        root = Path(tempfile.mkdtemp(prefix="routine-m2-proxy-", dir="/tmp/opencode"))
        name = "routine-proxy-component-" + uuid.uuid4().hex[:12]
        script = (PACKAGE / "tests/fixtures/proxy_component.py").read_text()
        command = docker + ["run", "--detach", "--pull", "never", "--name", name,
                            "--read-only", "--network", "none", "--cap-drop", "ALL",
                            "--security-opt", "no-new-privileges:true", "--user", "10001:10001",
                            "--memory", "96m", "--memory-swap", "96m", "--cpus", "0.25", "--pids-limit", "32",
                            "--log-driver", "local", "--log-opt", "max-size=1m", "--log-opt", "max-file=1",
                            "--log-opt", "compress=false", "--tmpfs", "/tmp:rw,size=8m,mode=1777",
                            "--entrypoint", "python3", image, "-B", "-c", script]
        record = {"image_id": image, "bundle_sha256": bundle_identity(), "container": name,
                  "probe_sha256": digest(script.encode()), "production_baseline_admitted": False}
        try:
            run_bounded(command, timeout=20)
            record["exit_code"] = int(run_bounded(docker + ["wait", name], timeout=35).strip())
            output = run_bounded(docker + ["logs", name], timeout=15, max_bytes=65536)
            record["output_sha256"] = digest(output)
            if record["exit_code"] == 0:
                record["result"] = json.loads(output)
            self.assertNotIn(b"private-proxy-output-canary", output)
        finally:
            subprocess.run(docker + ["stop", "--time", "5", name], env=host_environment(),
                           capture_output=True, timeout=15)
            inspection = run_bounded(docker + ["inspect", name], timeout=15)
            (root / "container-inspect.json").write_bytes(inspection)
            record["container_stopped"] = not json.loads(inspection)[0]["State"]["Running"]
            (root / "qualification.json").write_text(json.dumps(record, indent=2) + "\n")
            print(f"Proxy component evidence retained: {root}")
        self.assertEqual(record["exit_code"], 0, record)
        self.assertTrue(record["container_stopped"])
        self.assertTrue(record["result"]["passed"])
        self.assertFalse(record["result"]["host_firewall_qualified"])
        self.assertFalse(record["result"]["approved_external_access_qualified"])


if __name__ == "__main__":
    unittest.main()
