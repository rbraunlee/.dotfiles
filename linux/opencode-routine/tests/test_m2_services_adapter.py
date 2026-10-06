"""Injected Docker/network service lifecycle: never real Docker or credentials."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from test_m2_environment import environment_profile
from test_m2 import supported_daemon
from routine.contracts import RoutineError, canonical, parse_json
from routine.policy import environment_policy
from routine.service_adapters import ServiceEnvironmentAdapter, service_config, service_identity


class FakeNetwork:
    def __init__(self, calls):
        self.calls, self.fail, self.stop_result = calls, False, True

    def preflight(self, plan, timeout):
        self.calls.append("network-preflight")

    def create_networks(self, plan, timeout):
        self.calls.append("networks")

    def enforce_policy(self, plan, timeout):
        self.calls.append("policy")

    def component_networks(self, plan, component):
        return [{"logical_id": "internal", "network_id": "e" * 64,
                 "name": plan["networks"][0]["name"], "ipv4_address": "172.25.0.4"}]

    def verify_component(self, plan, component, inspect, timeout):
        self.calls.append("verify-network")
        assert type(inspect["State"]["Running"]) is bool
        if self.fail:
            raise RoutineError("policy_unavailable", "Fake pre-start enforcement refusal")
        return True

    def start_proxy(self, plan, timeout):
        self.calls.append("proxy-start")

    def wait_proxy_ready(self, plan, timeout):
        self.calls.append("proxy-ready")

    def stop_proxy(self, plan, timeout):
        self.calls.append("proxy-stop")
        return self.stop_result


def inspection(document):
    service = service_config(document)
    network = service["networks"]["internal"]
    return {"Id": "f" * 64, "Name": "/" + service["container_name"], "Image": service["image"],
        "Config": {"User": service["user"], "Labels": service["labels"], "Env": [], "Entrypoint": None,
                   "Cmd": ["/fake-server"], "WorkingDir": "", "Healthcheck": {"Test": ["NONE"]}},
        "State": {"Running": False, "Paused": False, "Restarting": False, "Status": "created", "Dead": False},
        "HostConfig": {"Init": True, "ReadonlyRootfs": True, "Privileged": False, "CapAdd": [], "CapDrop": ["ALL"],
                       "SecurityOpt": ["no-new-privileges:true"], "PortBindings": {}, "Devices": [], "DeviceRequests": [],
                       "ExtraHosts": [], "PidMode": "", "IpcMode": "private", "UTSMode": "", "UsernsMode": "",
                       "NetworkMode": document["networks"]["internal"]["name"], "RestartPolicy": {"Name": "no"},
                       "Memory": 512 * 1048576, "MemorySwap": 512 * 1048576, "PidsLimit": 128, "NanoCpus": 10**9,
                       "StorageOpt": {"size": "1024M"}, "LogConfig": {"Type": "local", "Config": {"max-size": "16m", "max-file": "1", "compress": "false"}},
                       "Dns": ["127.0.0.1"], "DnsSearch": ["."], "DnsOptions": ["ndots:0"], "VolumesFrom": [],
                       "Tmpfs": dict(item.split(":", 1) for item in service["tmpfs"])},
        "Mounts": [{"Type": "tmpfs", "Destination": item.split(":", 1)[0], "RW": True} for item in service["tmpfs"]] +
                  [{"Type": "bind", "Source": item["source"], "Destination": item["target"], "RW": False,
                    "Propagation": "rprivate"} for item in service["volumes"]],
        "NetworkSettings": {"Networks": {document["networks"]["internal"]["name"]: {
            "NetworkID": "e" * 64, "IPAddress": network["ipv4_address"], "GlobalIPv6Address": "",
            "Aliases": network["aliases"], "MacAddress": "02:00:00:00:00:04"}}}}


class FakeDocker:
    def __init__(self, calls):
        self.calls, self.value, self.documents = calls, None, []
        self.mutate, self.fail_create, self.existing, self.replace = None, False, False, False
        self.clock = None

    def docker(self, args, timeout, max_bytes=1048576):
        assert timeout > 0
        if args[0] == "info":
            return canonical(supported_daemon())
        if args[:2] == ["image", "inspect"]:
            return canonical([{"Id": args[2], "Config": {"Env": [], "Entrypoint": None, "Cmd": ["/fake-server"],
                                                        "WorkingDir": "", "Volumes": {}}}])
        if args[0] == "ps":
            return b"old-container" if self.existing else b""
        if args[0] == "inspect":
            self.calls.append("inspect")
            value = deepcopy(self.value)
            if self.replace:
                value["Id"] = "b" * 64
            return canonical([value])
        if args[0] == "start":
            self.calls.append("start:" + args[1])
            self.value["State"].update(Running=True, Status="running")
            return b""
        if args[0] == "exec":
            self.calls.append("exec:" + args[1])
            if self.clock is not None:
                self.clock[0] += timeout
            return b"fake-secret-output-NOT-EXPORTED"
        if args[0] == "stop":
            self.calls.append("stop:" + args[-1])
            self.value["State"].update(Running=False, Status="exited")
            return b""
        raise AssertionError(args)

    def compose(self, directory, artifact_id, args, timeout):
        self.calls.append("create")
        document = parse_json((Path(directory) / "compose.json").read_bytes())
        assert args == ["create", "--no-recreate", "--no-build", "--pull", "never", next(iter(document["services"]))]
        self.documents.append(document)
        self.value = inspection(document)
        if self.mutate:
            self.mutate(self.value)
        if self.fail_create:
            raise RoutineError("adapter_failed", "Fake ambiguous create")


class ServiceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="routine-services-", dir="/tmp/opencode")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = environment_policy(environment_profile(), "a" * 64)
        self.plan["services"][0]["resources"].update(memory_mb=512, pids=128, disk_mb=1024, log_mb=16, cpus=1)
        self.calls, self.events = [], []
        self.docker, self.network = FakeDocker(self.calls), FakeNetwork(self.calls)
        (self.root / self.plan["artifact_id"]).mkdir(mode=0o700)
        delivery = self.root / self.plan["artifact_id"] / "credentials"
        delivery.mkdir(mode=0o700)
        self.key = delivery / "fake-key"
        self.key.write_bytes(b"fake-service-delivery")
        self.key.chmod(0o444)
        self.adapter = ServiceEnvironmentAdapter(self.root, self.network, docker=self.docker,
            credential_path=lambda plan, binding: self.key,
            checkpoint=lambda plan, component, event, metadata: self.events.append((event, metadata)))

    def start(self, bindings=None):
        self.adapter.preflight(self.plan, 5)
        self.adapter.create_networks(self.plan, 5)
        self.adapter.enforce_policy(self.plan, 5)
        return self.adapter.start_component(self.plan, "service:database", self.plan["credentials"][:1] if bindings is None else bindings, 5)

    def test_create_stopped_verify_then_start_id_and_bounded_readiness(self):
        container_id = self.start()
        self.assertEqual(container_id, "f" * 64)
        self.assertLess(self.calls.index("create"), self.calls.index("verify-network"))
        self.assertLess(self.calls.index("verify-network"), self.calls.index("start:" + container_id))
        self.adapter.wait_ready(self.plan, "service:database", 5)
        self.assertIn("exec:" + container_id, self.calls)
        self.assertEqual([item[0] for item in self.events][:3], ["create-intent", "created", "start-intent"])
        self.assertNotIn("fake-secret-output", canonical(self.events).decode())
        self.assertTrue(self.adapter.stop_components(self.plan, ["service:database", "proxy"], 5))
        self.assertLess(self.calls.index("stop:" + container_id), self.calls.index("proxy-stop"))
        self.assertTrue((self.root / self.plan["artifact_id"]).is_dir())

    def test_failed_network_proof_never_starts_but_owned_created_container_stops(self):
        self.network.fail = True
        with self.assertRaises(RoutineError):
            self.start()
        self.assertFalse(any(call.startswith("start:") for call in self.calls))
        self.assertTrue(self.adapter.stop_components(self.plan, ["service:database"], 5))

    def test_effective_config_privilege_resource_mount_and_dns_drift_refused(self):
        mutations = [lambda v: v["HostConfig"].update(Privileged=True),
                     lambda v: v["HostConfig"].update(MemorySwap=0),
                     lambda v: v["HostConfig"].update(Dns=["8.8.8.8"]),
                     lambda v: v["HostConfig"].update(Tmpfs={}),
                     lambda v: v["Config"].update(Env=["FAKE_TOKEN=not-real"]),
                     lambda v: v["Mounts"].append({"Type": "bind", "Destination": "/socket", "Source": "/foreign", "RW": True}),
                     lambda v: v["NetworkSettings"]["Networks"].clear(),
                     lambda v: v["State"].update(Running=True)]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                self.setUp()
                self.docker.mutate = mutation
                with self.assertRaises(RoutineError):
                    self.start()
                self.assertFalse(any(call.startswith("start:") for call in self.calls))

    def test_preexisting_container_and_duplicate_start_never_replace_or_adopt(self):
        self.docker.existing = True
        with self.assertRaises(RoutineError):
            self.start()
        self.assertNotIn("create", self.calls)
        self.assertFalse(self.adapter.stop_components(self.plan, ["service:database"], 5))

    def test_ambiguous_create_is_stoppable_only_with_owned_nonce(self):
        self.docker.fail_create = True
        with self.assertRaises(RoutineError):
            self.start()
        self.assertTrue(self.adapter.stop_components(self.plan, ["service:database"], 5))

    def test_replaced_id_or_nonce_never_stops_foreign_work(self):
        self.start()
        self.docker.replace = True
        self.assertFalse(self.adapter.stop_components(self.plan, ["service:database"], 5))
        self.assertFalse(any(call.startswith("stop:") for call in self.calls))

    def test_provider_binding_and_unapproved_service_binding_never_reach_docker(self):
        for binding in (self.plan["credentials"][1], {**self.plan["credentials"][0], "ref": "foreign"}):
            with self.subTest(binding=binding), self.assertRaises(RoutineError):
                self.start([binding])
        self.assertNotIn("create", self.calls)

    def test_scoped_fake_delivery_path_is_read_only_and_never_in_checkpoint(self):
        root = self.root / self.plan["artifact_id"] / "credentials"
        key = root / "fake-key"
        self.adapter.credential_path = lambda plan, binding: key
        self.start([self.plan["credentials"][0]])
        volume = service_config(self.docker.documents[-1])["volumes"][0]
        self.assertTrue(volume["read_only"])
        self.assertEqual(volume["target"], self.plan["credentials"][0]["target"])
        self.assertNotIn(str(key), canonical(self.events).decode())
        self.assertNotIn("fake-service-delivery", canonical(self.events).decode())

    def test_missing_delivery_resolver_or_foreign_source_fails_closed(self):
        self.adapter.credential_path = None
        with self.assertRaises(RoutineError):
            self.start([self.plan["credentials"][0]])
        self.adapter.credential_path = lambda plan, binding: self.root / "foreign-key"
        with self.assertRaises(RoutineError):
            self.start([self.plan["credentials"][0]])
        self.assertNotIn("create", self.calls)

    def test_proxy_has_no_credentials_and_stop_requires_literal_true(self):
        self.adapter.preflight(self.plan, 5)
        self.adapter.create_networks(self.plan, 5)
        self.adapter.enforce_policy(self.plan, 5)
        self.adapter.start_component(self.plan, "proxy", [], 5)
        self.adapter.wait_ready(self.plan, "proxy", 5)
        with self.assertRaises(RoutineError):
            self.adapter.start_component(self.plan, "proxy", [self.plan["credentials"][0]], 5)
        self.network.stop_result = 1
        self.assertFalse(self.adapter.stop_components(self.plan, ["proxy"], 5))

    def test_intent_checkpoint_failure_has_no_create_effects(self):
        def fail(*args):
            raise OSError("fake-private-message")
        self.adapter.checkpoint = fail
        with self.assertRaises(OSError):
            self.start()
        self.assertNotIn("create", self.calls)

    def test_created_checkpoint_failure_still_allows_safe_stop(self):
        def fail(plan, component, event, metadata):
            if event == "created":
                raise OSError("fake-private-message")
        self.adapter.checkpoint = fail
        with self.assertRaises(OSError):
            self.start()
        self.assertTrue(self.adapter.stop_components(self.plan, ["service:database"], 5))

    def test_stopping_checkpoint_failure_does_not_skip_stop_but_is_unconfirmed(self):
        self.start()
        def fail(*args):
            raise OSError("fake-private-message")
        self.adapter.checkpoint = fail
        self.assertFalse(self.adapter.stop_components(self.plan, ["service:database"], 5))
        self.assertIn("stop:" + "f" * 64, self.calls)

    def test_late_readiness_success_is_failure_and_stop_budget_is_shared(self):
        clock = [0]
        self.adapter.monotonic = lambda: clock[0]
        self.docker.clock = clock
        self.start()
        with self.assertRaises(RoutineError) as error:
            self.adapter.wait_ready(self.plan, "service:database", 1)
        self.assertEqual(error.exception.code, "command_timeout")
        self.assertTrue(self.adapter.stop_components(self.plan, ["service:database"], 5))

    def test_readiness_cannot_expand_its_profile_command_deadline(self):
        self.start()
        clock = [0]
        self.adapter.monotonic = lambda: clock[0]
        self.docker.clock = clock
        with self.assertRaises(RoutineError) as error:
            self.adapter.wait_ready(self.plan, "service:database", 100)
        self.assertEqual(error.exception.code, "command_timeout")
        self.assertEqual(clock[0], self.plan["services"][0]["readiness"]["timeout_seconds"])

    def test_plan_drift_and_mutable_attachment_fragments_are_rejected(self):
        self.start()
        changed = deepcopy(self.plan)
        changed["services"][0]["ports"].append(9999)
        with self.assertRaises(RoutineError):
            self.adapter.wait_ready(changed, "service:database", 5)
        self.assertFalse(self.adapter.stop_components(changed, ["service:database"], 5))

    def test_attachment_fields_and_extra_egress_network_are_refused_before_create(self):
        attachment = self.network.component_networks(self.plan, "service:database")[0]
        for values in ([{**attachment, "aliases": ["host"]}], [{**attachment, "logical_id": "egress"}],
                       [{**attachment, "name": "foreign-network"}], [attachment, attachment],
                       [{**attachment, "ipv4_address": "127.0.0.1"}]):
            with self.subTest(values=values):
                self.network.component_networks = lambda plan, component, values=values: values
                with self.assertRaises(RoutineError):
                    self.start()
                self.assertNotIn("create", self.calls)

    def test_literal_network_refusal_cannot_become_readiness(self):
        self.network.verify_component = lambda *args: False
        with self.assertRaises(RoutineError):
            self.start()
        self.assertFalse(any(call.startswith("start:") for call in self.calls))
        self.assertTrue(self.adapter.stop_components(self.plan, ["service:database"], 5))

    def test_network_proof_cannot_hide_configuration_change_before_start(self):
        def proof(*args):
            self.docker.value["HostConfig"]["Dns"] = ["8.8.8.8"]
        self.network.verify_component = proof
        with self.assertRaises(RoutineError):
            self.start()
        self.assertFalse(any(call.startswith("start:") for call in self.calls))

    def test_duplicate_start_and_nonce_replacement_hold_dispatch(self):
        self.start()
        with self.assertRaises(RoutineError):
            self.start()
        self.assertEqual(self.calls.count("create"), 1)
        self.docker.value["Config"]["Labels"]["routine.launch-id"] = "0" * 32
        self.assertFalse(self.adapter.stop_components(self.plan, ["service:database"], 5))
        self.assertFalse(any(call.startswith("stop:") for call in self.calls))

    def test_missing_service_delivery_and_changed_readonly_mount_are_refused(self):
        with self.assertRaises(RoutineError):
            self.start([])
        self.assertNotIn("create", self.calls)
        def writable(value):
            next(item for item in value["Mounts"] if item["Type"] == "bind")["RW"] = True
        self.docker.mutate = writable
        with self.assertRaises(RoutineError):
            self.start()
        self.assertFalse(any(call.startswith("start:") for call in self.calls))

    def test_inherited_image_volumes_fail_preflight(self):
        docker = self.docker.docker
        def volumes(args, timeout, max_bytes=1048576):
            value = docker(args, timeout, max_bytes)
            if args[:2] == ["image", "inspect"]:
                image = parse_json(value)
                image[0]["Config"]["Volumes"] = {"/data": {}}
                return canonical(image)
            return value
        self.docker.docker = volumes
        with self.assertRaises(RoutineError):
            self.start()
        self.assertNotIn("networks", self.calls)

    def test_unconfirmed_service_stop_does_not_skip_proxy_stop(self):
        self.start()
        docker = self.docker.docker
        def fail(args, timeout, max_bytes=1048576):
            if args[0] == "stop":
                raise RoutineError("command_timeout", "Fake stop refusal")
            return docker(args, timeout, max_bytes)
        self.docker.docker = fail
        self.assertFalse(self.adapter.stop_components(self.plan, ["service:database", "proxy"], 5))
        self.assertIn("proxy-stop", self.calls)

    def test_shared_stop_deadline_cannot_reset_for_proxy(self):
        self.start()
        clock = [0]
        self.adapter.monotonic = lambda: clock[0]
        docker = self.docker.docker
        def late(args, timeout, max_bytes=1048576):
            value = docker(args, timeout, max_bytes)
            if args[0] == "stop":
                clock[0] += timeout
            return value
        self.docker.docker = late
        self.assertFalse(self.adapter.stop_components(self.plan, ["service:database", "proxy"], 5))
        self.assertNotIn("proxy-stop", self.calls)

    def test_unknown_component_and_unenforced_policy_never_start(self):
        self.adapter.preflight(self.plan, 5)
        with self.assertRaises(RoutineError):
            self.adapter.start_component(self.plan, "service:database", self.plan["credentials"][:1], 5)
        self.adapter.enforce_policy(self.plan, 5)
        with self.assertRaises(RoutineError):
            self.adapter.start_component(self.plan, "service:unknown", [], 5)
        self.assertNotIn("create", self.calls)

    def test_unexpected_alias_and_malformed_inspection_fail_closed(self):
        for mutate in (lambda value: value["Config"].update(Healthcheck=None),
                       lambda value: value["HostConfig"].update(RestartPolicy=None),
                       lambda value: next(iter(value["NetworkSettings"]["Networks"].values()))["Aliases"].append("host")):
            with self.subTest(mutate=mutate):
                self.setUp()
                self.docker.mutate = mutate
                with self.assertRaises(RoutineError):
                    self.start()
                self.assertFalse(any(call.startswith("start:") for call in self.calls))
