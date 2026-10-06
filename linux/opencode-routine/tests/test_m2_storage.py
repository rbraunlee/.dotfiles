"""Full-layer transport contracts and explicitly opted-in retained baseline probes."""
import errno
import io
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

import test_m1 as fixtures
import test_m2 as m2
from routine.compose import DockerCompose, bundle_identity, compose_document
from routine.contracts import RoutineError, canonical, digest
from routine.launcher import Launcher
from routine.inputs import open_source
from routine.retention import StorageBinding, source_from_inspection
from routine.sandbox import Sandbox
from routine.store import Store
from routine.transfer import export_bundle

worker = m2.worker

class EvidenceTransportTests(unittest.TestCase):
    def test_full_layer_still_emits_only_the_allowlisted_record(self):
        value = {"outcome": "failed", "diagnostic": "bootstrap_failed"}
        output = io.BytesIO()
        with patch.object(worker, "EVIDENCE", Path("/unavailable/evidence.json")), \
             patch.object(Path, "open", side_effect=OSError(errno.ENOSPC, "private-secret-canary")), \
             patch.object(worker.sys, "stdout") as stdout:
            stdout.buffer = output
            worker.write_evidence(value)
        self.assertEqual(json.loads(output.getvalue()), {"routine_evidence": value})
        self.assertNotIn(b"private-secret-canary", output.getvalue())

    def test_local_evidence_is_retained_when_space_exists(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as directory:
            path = Path(directory) / "evidence.json"
            value = {"outcome": "failed"}
            with patch.object(worker, "EVIDENCE", path), patch.object(worker.sys, "stdout") as stdout:
                stdout.buffer = io.BytesIO()
                worker.write_evidence(value)
            self.assertEqual(json.loads(path.read_bytes()), value)
            self.assertFalse(path.with_suffix(".tmp").exists())

    def test_collection_uses_bounded_logs_without_a_layer_mount(self):
        calls = []
        value = {"outcome": "failed"}
        def run(args, **limits):
            calls.append((args, limits))
            return canonical({"routine_evidence": value}) + b"\n"
        result = DockerCompose(run=run).collect("a" * 64, 1024, 10)
        self.assertEqual(result, value)
        self.assertEqual(calls[0][0][-2:], ["logs", "routine-" + "a" * 32])
        self.assertEqual(calls[0][1]["max_bytes"], 1088)
        self.assertEqual(len(calls), 1)

    def test_nonempty_bad_or_multiple_log_records_never_fall_back_to_archive(self):
        record = canonical({"routine_evidence": {"outcome": "failed"}})
        for data in (b"raw-secret-output\n" + record, record + b"\n" + record,
                     b'{"routine_evidence":{},"routine_evidence":{}}',
                     canonical({"routine_evidence": {}, "raw_output": "secret"}), b"{}", record[:-1]):
            calls = []
            def run(args, **limits):
                calls.append(args)
                return data
            with self.subTest(data=data), self.assertRaises(RoutineError):
                DockerCompose(run=run).collect("a" * 64, 1024, 10)
            self.assertEqual(len(calls), 1)

    def test_empty_legacy_logs_use_archive_with_the_remaining_deadline(self):
        clock, calls = [0], []
        def run(args, **limits):
            calls.append((args, limits))
            clock[0] += 1
            return b""
        with patch("routine.compose.read_evidence_archive", return_value={"legacy": True}) as read:
            self.assertEqual(DockerCompose(run=run, monotonic=lambda: clock[0]).collect("a" * 64, 1024, 5),
                             {"legacy": True})
        self.assertEqual(calls[1][1]["timeout"], 4)
        self.assertIn("cp", calls[1][0])
        read.assert_called_once_with(b"", 1024)

    def test_oversized_or_late_evidence_cannot_pass(self):
        data = canonical({"routine_evidence": {"padding": "x" * 200}})
        with self.assertRaises(RoutineError) as caught:
            DockerCompose(run=lambda *a, **kw: data).collect("a" * 64, 100, 5)
        self.assertEqual(caught.exception.code, "output_limit")
        clock = [0]
        def run(*args, **limits):
            clock[0] = 6
            return canonical({"routine_evidence": {}})
        with self.assertRaises(RoutineError) as caught:
            DockerCompose(run=run, monotonic=lambda: clock[0]).collect("a" * 64, 1024, 5)
        self.assertEqual(caught.exception.code, "command_timeout")


class WorkerOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir="/tmp/opencode")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.artifact_id = "a" * 64
        self.profile = fixtures.profile()
        self.profile.update(version=2, runtime={"image": "sha256:" + "c" * 64, "opencode_version": "2.0.22"})
        self.document = compose_document(self.profile, self.directory / "handoff", self.artifact_id)
        (self.directory / "compose.json").write_bytes(canonical(self.document))
        self.value = {"Id": "d" * 64, "Name": "/routine-" + self.artifact_id[:32],
                      "Image": self.profile["runtime"]["image"], "State": {"Running": False, "ExitCode": 0},
                      "Config": {"Labels": dict(self.document["services"]["worker"]["labels"])}}
        self.calls = []

    def adapter(self, existing=False):
        def run(args, **limits):
            self.calls.append((args, limits))
            if "ps" in args:
                return b"existing-id\n" if existing else b""
            if "inspect" in args:
                return canonical([self.value])
            return b""
        return DockerCompose(run=run)

    def test_existing_name_is_never_replaced_started_or_stopped(self):
        adapter = self.adapter(existing=True)
        with self.assertRaises(RoutineError) as caught:
            adapter.start(self.directory, self.artifact_id, 10)
        self.assertEqual(caught.exception.code, "recovery_required")
        self.assertEqual(len(self.calls), 1)
        self.value["Config"]["Labels"]["routine.launch-id"] = "f" * 32
        with self.assertRaises(RoutineError):
            adapter.stop(self.directory, self.artifact_id)
        self.assertFalse(any("start" in args or "stop" in args or "create" in args for args, _ in self.calls))

    def test_creation_race_cannot_adopt_or_replace_an_earlier_preparation(self):
        self.value["Config"]["Labels"]["routine.launch-id"] = "f" * 32
        adapter = self.adapter()
        with self.assertRaises(RoutineError):
            adapter.start(self.directory, self.artifact_id, 10)
        creation = self.calls[1][0]
        self.assertIn("create", creation)
        self.assertIn("--no-recreate", creation)
        with self.assertRaises(RoutineError):
            adapter.stop(self.directory, self.artifact_id)
        self.assertFalse(any("start" in args or "stop" in args for args, _ in self.calls))

    def test_worker_start_and_stop_use_verified_immutable_id_and_retain_layer(self):
        adapter = self.adapter()
        adapter.start(self.directory, self.artifact_id, 10)
        adapter.stop(self.directory, self.artifact_id)
        for args, _ in self.calls:
            if "start" in args or "stop" in args:
                self.assertEqual(args[-1], self.value["Id"])
        self.assertFalse(any(arg in ("up", "down", "rm", "prune") for args, _ in self.calls for arg in args))

    def test_replaced_container_id_is_refused_before_stopping(self):
        adapter = self.adapter()
        adapter.start(self.directory, self.artifact_id, 10)
        self.value["Id"] = "e" * 64
        with self.assertRaises(RoutineError):
            adapter.stop(self.directory, self.artifact_id)
        self.assertFalse(any("stop" in args for args, _ in self.calls))


@unittest.skipUnless(os.environ.get("OPENCODE_ROUTINE_STORAGE_IMAGE"),
                     "Retained production storage tests require an approved pinned image and Docker access")
class LiveStorageTests(unittest.TestCase):
    write = fixtures.M1Tests.write
    fixture = fixtures.M1Tests.fixture
    save_manifest = fixtures.M1Tests.save_manifest
    authorize = fixtures.M1Tests.authorize
    prepare_profile = m2.M2Tests.prepare_profile
    git = staticmethod(m2.M2Tests.git)

    def setUp(self):
        # Intentionally keep the entire fixture, authority and handoff, including
        # failures. No cleanup/reset/prune; each test gets a distinct run identity.
        self.base = Path(tempfile.mkdtemp(prefix="routine-m2-storage-", dir="/tmp/opencode"))
        self.root = self.base / "project"
        self.root.mkdir()
        self.store = Store(self.base / "state")
        self.launcher = Launcher(self.store)
        self.manifest = self.fixture("feature")
        self.profile = fixtures.profile()
        self.profile.update(version=2, runtime={"image": os.environ["OPENCODE_ROUTINE_STORAGE_IMAGE"],
                                                "opencode_version": "2.0.22"})
        self.profile["resources"].update(memory_mb=768, disk_mb=128, log_mb=1)
        self.empty_template = self.base / "empty-template"
        self.empty_template.mkdir()
        self.git("init", "-q", "--template=" + str(self.empty_template), str(self.root))
        self.write("README.md", b"# Retained storage fixture\n")
        self.git("-C", str(self.root), "add", "README.md")
        self.git("-C", str(self.root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                 "commit", "-q", "-m", "Storage fixture")
        self.manifest["baseline"]["commit"] = self.git("-C", str(self.root), "rev-parse", "HEAD").decode().strip()
        self.run_id = "probe-" + uuid.uuid4().hex

    def launch(self, script, setup=False, timeout=30, expect_held=False):
        entry = {"argv": ["python3", "-c", script], "timeout_seconds": timeout}
        self.profile["commands"] = {"setup": [entry] if setup else [],
                                    "checks": {"probe": {"argv": ["true"], "timeout_seconds": 10} if setup else entry}}
        self.prepare_profile()
        authorization = self.authorize()
        test = self
        class CheckedAuthority(DockerCompose):
            def wait(adapter, artifact_id, timeout):
                before = {path.name: digest(path.read_bytes()) for path in test.store.root.iterdir() if path.is_file()}
                memory_fd = None
                observer = None
                done = threading.Event()
                if getattr(test, 'observe_memory', False) and not hasattr(test, 'memory_observation'):
                    value = json.loads(adapter.docker(['inspect', adapter.containers[artifact_id]], 10))[0]
                    pid = value['State']['Pid']
                    assert type(pid) is int and pid > 0
                    membership = Path(f'/proc/{pid}/cgroup').read_text()
                    match = re.fullmatch(r'0::(/[A-Za-z0-9_./-]+)\n', membership)
                    assert match and '..' not in Path(match.group(1)).parts
                    cgroup = match.group(1).removeprefix('/')
                    assert adapter.containers[artifact_id] in cgroup
                    limits = {}
                    for name in ('memory.max', 'memory.swap.max'):
                        fd = open_source('/sys/fs/cgroup', cgroup + '/' + name)
                        try:
                            limits[name] = int(os.read(fd, 128))
                        finally:
                            os.close(fd)
                    memory_fd = open_source('/sys/fs/cgroup', cgroup + '/memory.events')
                    initial = {key: int(value) for key, value in (line.split() for line in os.read(memory_fd, 4096).decode().splitlines())}
                    test.memory_observation = {'limits': limits, 'before': initial, 'maximum': dict(initial)}
                    def observe():
                        while not done.is_set():
                            try:
                                os.lseek(memory_fd, 0, os.SEEK_SET)
                                events = {key: int(value) for key, value in (line.split() for line in os.read(memory_fd, 4096).decode().splitlines())}
                                for key, value in events.items():
                                    test.memory_observation['maximum'][key] = max(value, test.memory_observation['maximum'].get(key, 0))
                            except OSError:
                                # The owned cgroup disappears when the container exits;
                                # absence is not enforcement proof. Require a captured
                                # positive event below, never infer OOM from API failure.
                                return
                            done.wait(0.01)
                    observer = threading.Thread(target=observe, daemon=True)
                    observer.start()
                try:
                    code = super().wait(artifact_id, timeout)
                finally:
                    done.set()
                    if observer is not None:
                        observer.join(timeout=2)
                        test.assertFalse(observer.is_alive())
                    if memory_fd is not None:
                        os.close(memory_fd)
                after = {path.name: digest(path.read_bytes()) for path in test.store.root.iterdir() if path.is_file()}
                test.assertEqual(before, after)
                return code
        adapter = CheckedAuthority()
        with self.launcher.coordinator("project", "feature", "coordinator") as session:
            session.claim("01", self.run_id, authorization)
            result = Sandbox(adapter, export_bundle).launch(session, self.run_id)
            if expect_held:
                with self.assertRaises(RoutineError) as caught:
                    Sandbox(adapter, export_bundle).launch(session, self.run_id)
                self.assertEqual(caught.exception.code, "recovery_required")
            else:
                duplicate = Sandbox(adapter, export_bundle).launch(session, self.run_id)
                self.assertTrue(duplicate["existing"])
                self.assertEqual(result["run"], duplicate["run"])
        artifact_id = result["run"]["artifact_id"]
        inspection = json.loads(adapter.docker(["inspect", "routine-" + artifact_id[:32]], 10))[0]
        daemon = json.loads(adapter.docker(["info", "--format", "{{json .}}"], 10))
        if not expect_held:
            self.assertEqual(result["run"]["container_id"], inspection["Id"])
            admitted = source_from_inspection(StorageBinding(daemon["DockerRootDir"], daemon["ID"]),
                                              daemon, inspection, result["run"])
            self.assertEqual(admitted.container_id, inspection["Id"])
        qualification = {"version": 1, "run": result["run"], "bundle_sha256": bundle_identity(),
                         "probe_sha256": digest(script.encode()), "test_sha256": digest(Path(__file__).read_bytes()),
                         "host_assets": {path.name: digest(path.read_bytes()) for path in
                                         (fixtures.LIBRARY / "routine").glob("*.py")},
                         "daemon": daemon, "retention_source_metadata_validated": not expect_held,
                         "daemon_restart_qualified": False, "full_layer_checkout_recovery_qualified": False}
        for name, value in (("qualification.json", qualification), ("container-inspect.json", inspection)):
            path = self.base / name
            path.write_bytes(canonical(value))
            path.chmod(0o600)
        print("Retained storage qualification:", self.base)
        self.assertEqual(result["run"]["result"]["container_stopped"], not expect_held, result)
        self.assertFalse(inspection["State"]["Running"])
        self.assertEqual(inspection["HostConfig"]["StorageOpt"], {"size": "128M"})
        return result["run"], adapter

    def retain_observations(self, **values):
        path = self.base / "qualification.json"
        qualification = json.loads(path.read_bytes())
        qualification["observations"] = values
        path.write_bytes(canonical(qualification))

    def test_full_layer_failure_evidence_is_collected_without_freeing_checkout_bytes(self):
        script = "\n".join([
            "import errno,os,pathlib",
            "pathlib.Path('retained-before-fill').write_text('checkout retained')",
            "data=b'x'*65536",
            "fd=os.open('quota-fill.bin',os.O_CREAT|os.O_WRONLY,0o600)",
            "written=0",
            "try:",
            " for _ in range(4096):",  # finite 256 MiB attempt under a 128 MiB cap
            "  written+=os.write(fd,data)",
            "  os.fsync(fd)",
            "except OSError as error:",
            " assert error.errno in (errno.ENOSPC,errno.EDQUOT)",
            " print('quota-enforced',written,flush=True)",
            "else:",
            " raise AssertionError('quota not enforced')",
            "finally:",
            " os.close(fd)",
            "raise SystemExit(1)",
        ])
        run, adapter = self.launch(script)
        self.assertEqual(run["state"], "sandbox-failed", run)
        self.assertIsNotNone(run["result"]["evidence_sha256"], run)
        directory = self.store.root / "artifacts" / run["artifact_id"]
        evidence = json.loads((directory / "evidence.json").read_bytes())
        self.assertEqual(evidence["outcome"], "failed")
        self.assertIsNotNone(evidence["service"])
        logs = adapter.docker(["logs", "routine-" + run["artifact_id"][:32]], 10)
        self.assertNotIn(b"quota-enforced", logs)  # no raw shell diagnostics
        # The original fault remains reproducible: no truncation/deletion/quota
        # increase was used to make collection pass. Keep this failed full layer.
        with self.assertRaises(RoutineError):
            adapter.docker(["cp", "routine-" + run["artifact_id"][:32] + ":/home/worker/project/retained-before-fill", "-"], 10)
        self.retain_observations(evidence_collected_without_layer_mount=True, stopped_layer_archive_read_failed=True,
                                 checkout_bytes_deleted=False, quota_increased=False)

    def test_setup_failure_retains_diagnostics_and_never_runs_checks(self):
        run, _ = self.launch("print('secret-output-canary');raise SystemExit(7)", setup=True)
        self.assertEqual(run["state"], "sandbox-failed", run)
        self.assertEqual(run["result"]["diagnostic"], "required_command_failed")
        evidence = (self.store.root / "artifacts" / run["artifact_id"] / "evidence.json").read_bytes()
        self.assertNotIn(b"secret-output-canary", evidence)
        self.assertEqual(len(json.loads(evidence)["checks"]), 1)
        self.retain_observations(setup_exit=7, checks_executed=False, raw_output_exported=False)

    def test_setup_timeout_retains_checkout_and_confirms_stopping(self):
        run, _ = self.launch("import time;time.sleep(30)", setup=True, timeout=1)
        self.assertEqual(run["state"], "sandbox-failed", run)
        self.assertEqual(run["result"]["diagnostic"], "required_command_failed")
        evidence = json.loads((self.store.root / "artifacts" / run["artifact_id"] / "evidence.json").read_bytes())
        self.assertEqual(evidence["checks"][0]["status"], "timeout")
        self.retain_observations(setup_timed_out=True, checks_executed=False)

    def test_state_denial_and_positive_checkout_retention_through_launcher(self):
        script = "\n".join([
            "import os,pathlib",
            "assert os.geteuid()==10001",
            f"root=pathlib.Path({str(self.store.root)!r})",
            f"for name in ('ledger.json','ledger.lock','coordinator-{digest(b'project/feature')}.lock'):",
            " for mode in ('rb','wb'):",
            "  try:",
            "   (root/name).open(mode)",
            "  except OSError:",
            "   pass",
            "  else:",
            "   raise AssertionError('host authority accessible')",
            "assert pathlib.Path('.git').is_dir()",
            "assert not pathlib.Path('.git/objects/info/alternates').exists()",
            "pathlib.Path('retention-marker').write_text('independent checkout')",
        ])
        run, adapter = self.launch(script)
        self.assertEqual(run["state"], "baseline-passed", run)
        archive = adapter.docker(["cp", "routine-" + run["artifact_id"][:32] + ":/home/worker/project/retention-marker", "-"], 10)
        import tarfile
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            self.assertEqual(stream.extractfile(stream.getmembers()[0]).read(), b"independent checkout")
        self.retain_observations(host_ledger_and_lock_access_denied=True, authority_unchanged_during_worker=True,
                                 stopped_checkout_marker_verified=True)

    def test_preexisting_container_is_held_without_adoption_replacement_or_stop(self):
        artifact_id = digest(("project/" + self.run_id).encode())
        adapter = DockerCompose()
        container_id = adapter.docker([
            "create", "--name", "routine-" + artifact_id[:32], "--network", "none", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "10001:10001", "--memory", "768m",
            "--memory-swap", "768m", "--cpus", "1", "--pids-limit", "64", "--storage-opt", "size=128M",
            "--log-driver", "local", "--log-opt", "max-size=1m", "--log-opt", "max-file=1", "--log-opt", "compress=false",
            "--label", "routine.artifact-id=" + artifact_id, "--label", "routine.launch-id=" + "f" * 32,
            "--entrypoint", "/usr/bin/true", self.profile["runtime"]["image"]], 15).decode().strip()
        before = adapter.docker(["inspect", container_id], 10)
        run, _ = self.launch("raise AssertionError('must not execute')", expect_held=True)
        self.assertEqual(run["state"], "sandbox-held", run)
        self.assertEqual(adapter.docker(["inspect", container_id], 10), before)
        self.retain_observations(preexisting_container_unchanged=True, adoption_or_replacement=False)

    def test_production_cpu_limit_actually_throttles_service_tool_command(self):
        self.profile['resources']['cpus'] = 0.25
        script = '\n'.join([
            'import pathlib,time',
            "root=pathlib.Path('/sys/fs/cgroup')",
            "quota,period=map(int,(root/'cpu.max').read_text().split())",
            'assert quota/period==0.25',
            "def counters(): return {k:int(v) for k,v in (line.split() for line in (root/'cpu.stat').read_text().splitlines())}",
            'before=counters()',
            'end=time.monotonic()+3',
            'while time.monotonic()<end: pass',
            "assert counters()['nr_throttled']>before['nr_throttled']",
        ])
        run, _ = self.launch(script)
        self.assertEqual(run['state'], 'baseline-passed', run)
        self.retain_observations(cpu_quota_cores=0.25, throttling_verified_inside_service_command=True)

    def test_production_memory_oom_is_enforced_and_retains_success_or_safe_failure(self):
        self.observe_memory = True
        script = '\n'.join([
            'import pathlib,subprocess,sys',
            "root=pathlib.Path('/sys/fs/cgroup')",
            "assert int((root/'memory.max').read_text())==768*1024**2",
            "assert (root/'memory.swap.max').read_text().strip()=='0'",
            "def counters(): return {k:int(v) for k,v in (line.split() for line in (root/'memory.events').read_text().splitlines())}",
            'before=counters()',
            "child=subprocess.Popen([sys.executable,'-B','-c','chunks=[]\\nfor _ in range(128): chunks.append(bytearray(8*1024**2))'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)",
            'try:',
            ' code=child.wait(timeout=20)',
            'finally:',
            ' if child.poll() is None:',
            '  child.kill()',
            '  child.wait(timeout=5)',
            "assert code==-9 and counters()['oom_kill']>before['oom_kill']",
        ])
        run, _ = self.launch(script)
        observed = self.memory_observation
        self.assertEqual(observed['limits'], {'memory.max': 768*1024**2, 'memory.swap.max': 0})
        self.assertGreater(observed['maximum']['oom_kill'], observed['before']['oom_kill'])
        self.assertIn(run['state'], ('baseline-passed', 'sandbox-failed'), run)
        self.assertIsNotNone(run['result']['evidence_sha256'], run)
        if run['state'] == 'sandbox-failed':
            self.assertIsNotNone(run['result']['diagnostic'])
        self.retain_observations(memory_limit_bytes=768*1024**2, finite_requested_bytes=1024*1024**2,
                                 host_cgroup_observation=observed, cgroup_oom_kill_verified=True,
                                 kernel_victim_not_assumed=True, baseline_outcome=run['state'])

    def test_production_pid_limit_rejects_finite_children_and_reaps_them(self):
        script = '\n'.join([
            'import errno,pathlib,subprocess,sys',
            "root=pathlib.Path('/sys/fs/cgroup')",
            "assert (root/'pids.max').read_text().strip()=='64'",
            "def counters(): return {k:int(v) for k,v in (line.split() for line in (root/'pids.events').read_text().splitlines())}",
            "before=counters()['max']",
            'children=[]',
            'denied=False',
            'try:',
            ' for _ in range(128):',
            '  try:',
            "   children.append(subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(20)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))",
            '  except OSError as error:',
            '   assert error.errno==errno.EAGAIN',
            '   denied=True',
            '   break',
            " assert denied and counters()['max']>before",
            'finally:',
            ' for child in children: child.kill()',
            ' for child in children: child.wait(timeout=5)',
            'assert all(child.poll() is not None for child in children)',
        ])
        run, _ = self.launch(script)
        self.assertEqual(run['state'], 'baseline-passed', run)
        self.retain_observations(pid_limit=64, finite_creation_attempts=128,
                                 eagain_and_cgroup_limit_event_verified=True, owned_children_reaped=True)


if __name__ == "__main__":
    unittest.main()
