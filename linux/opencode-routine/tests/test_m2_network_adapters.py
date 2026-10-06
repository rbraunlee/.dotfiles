"""Offline Docker API/nftables/DNS/bootstrap transaction tests. No live opt-ins."""
from copy import deepcopy
import tempfile
import unittest

from test_m2_environment import environment_profile
from routine.contracts import RoutineError, canonical
from routine.policy import environment_policy
from routine.networking import NetworkAdapter
from routine.network_transport import DockerNetworkTransport, NetworkAdminTransport
from routine.network_proxy import healthcheck


class Harness:
    """Independent decoded administration endpoints; no socket/process access."""
    def __init__(self):
        self.calls, self.events, self.networks, self.containers = [], [], {}, {}
        self.clock = 0
        self.firewall, self.dns, self.identities = None, {}, {}
        self.mutate = None
        self.collision = False

    def inventory(self, payload):
        return {"daemon_id": "daemon-1", "boot_id": "11111111-1111-1111-1111-111111111111", "observation_id": "e" * 64,
                "backend": "nftables-json", "bootstrap_interlock": True, "bridge_conntrack": True,
                "hook_priorities": {"conntrack": -200, "routine_filter": -150, "docker_accept": 0, "dns_output": -300, "docker_dns_dnat": -100},
                "enforcement_points": ["host-input", "host-forward-before-docker-accept", "same-bridge", "container-dns"],
                "host_addresses": ["192.168.1.20", "9.9.9.9"], "connected_routes": ["192.168.1.0/24", "9.9.9.0/24"],
                "allocations": [{"logical_id": network["id"], "subnet": f"172.30.{index}.0/24", "gateway": f"172.30.{index}.1",
                                 "bridge": "routinebr" + str(index),
                                 "addresses": {member: f"172.30.{index}.{offset}" for offset, member in enumerate(network["members"], 10)}}
                                for index, network in enumerate(payload["networks"])]}

    def finish(self, operation, result):
        if self.mutate:
            result = self.mutate(operation, deepcopy(result))
        return deepcopy(result)

    def docker(self, method, path, body, timeout):
        self.calls.append((method, path, deepcopy(body), timeout))
        self.assert_timeout(timeout)
        if path == "/info":
            result = {"ID": "daemon-1"}
        elif method == "GET" and path.startswith("/networks?"):
            result = [{"Id": "f" * 64}] if self.collision else []
        elif method == "POST" and path == "/networks/create":
            network_id = str(len(self.networks) + 1) * 64
            self.networks[network_id] = {**deepcopy(body), "Id": network_id, "Containers": {}}
            result = {"Id": network_id, "Warning": ""}
        elif method == "GET" and path.startswith("/networks/"):
            result = self.networks[path.rsplit("/", 1)[1]]
        elif method == "GET" and path.startswith("/images/"):
            result = {"Id": "sha256:" + "c" * 64, "Config": {"Labels": {"routine.bundle-sha256": "b" * 64, "routine.opencode-version": "2.0.22"}}}
        elif method == "GET" and path.startswith("/containers/json?"):
            result = [{"Id": "f" * 64}] if self.collision else []
        elif method == "POST" and path.startswith("/containers/create?"):
            container_id = "3" * 64
            from urllib.parse import parse_qs, urlparse
            name = parse_qs(urlparse(path).query)["name"][0]
            value = {"Id": container_id, "Name": "/" + name, "Image": body["Image"],
                     "Config": {key: deepcopy(value) for key, value in body.items() if key not in ("HostConfig", "NetworkingConfig")},
                     "HostConfig": deepcopy(body["HostConfig"]), "State": {"Running": False, "Paused": False, "Restarting": False},
                     "Mounts": [{"Type": "bind", "Source": body["HostConfig"]["Mounts"][0]["Source"],
                                 "Destination": "/policy/proxy.json", "RW": False}],
                     "NetworkSettings": {"Networks": {}, "Ports": {}}}
            for index, (name, entry) in enumerate(body["NetworkingConfig"]["EndpointsConfig"].items(), 1):
                value["NetworkSettings"]["Networks"][name] = {"NetworkID": entry["NetworkID"], "IPAddress": entry["IPAMConfig"]["IPv4Address"],
                    "GlobalIPv6Address": "", "LinkLocalIPv6Address": "", "Aliases": [], "Links": [],
                    "MacAddress": "02:00:00:00:00:0" + str(index), "EndpointID": str(index + 5) * 64}
                self.networks[entry["NetworkID"]]["Containers"][container_id] = {"IPv4Address": entry["IPAMConfig"]["IPv4Address"] + "/24", "IPv6Address": ""}
            self.containers[container_id] = value
            result = {"Id": container_id, "Warnings": []}
        elif method == "GET" and path.startswith("/containers/") and path.endswith("/json"):
            result = self.containers[path.split("/")[2]]
        elif method == "POST" and path.endswith("/start"):
            value = self.containers[path.split("/")[2]]
            value["State"]["Running"] = True
            value["State"]["Health"] = {"Status": "healthy"}
            result = None
        elif method == "POST" and "/stop?" in path:
            self.containers[path.split("/")[2]]["State"]["Running"] = False
            result = None
        else:
            raise AssertionError((method, path))
        return self.finish(path, result)

    @staticmethod
    def assert_timeout(value):
        assert 0 < value <= 30

    def admin(self, operation, payload, timeout):
        self.calls.append((operation, deepcopy(payload), timeout))
        self.assert_timeout(timeout)
        if operation == "host_inventory":
            result = self.inventory(payload)
            self.host_identity = {key: deepcopy(result[key]) for key in ("daemon_id", "boot_id", "observation_id", "host_addresses", "connected_routes", "hook_priorities")}
        elif operation == "read_host_identity":
            result = self.host_identity
        elif operation == "observe_network":
            result = {**payload, "bridge_ifindex": 100 + int(payload["bridge"][-1])}
        elif operation == "apply_firewall":
            self.firewall = deepcopy(payload)
            result = {"ok": True}
        elif operation == "read_firewall":
            result = self.firewall
        elif operation in ("prepare_held_component", "observe_component"):
            container_id = payload["container_id"]
            if container_id not in self.identities:
                self.identities[container_id] = {"container_id": container_id, "boot_id": payload["boot_id"],
                    "namespace_inode": 1000 + len(self.identities), "namespace_device": 4, "consumer_start_interlocked": True,
                    "survives_consumer_start": True, "workload_held": True,
                    "endpoints": [{**entry, "bridge_ifindex": 100 + (1 if entry["logical_id"] == "egress" else 0),
                        "host_ifindex": 200 + index + 10 * len(self.identities), "container_ifindex": 2 + index,
                        "host_veth": "veth" + str(len(self.identities)) + str(index),
                        "mac": self.containers[container_id]["NetworkSettings"]["Networks"][entry["name"]]["MacAddress"]}
                        for index, entry in enumerate(payload["attachments"])]}
            result = self.identities[container_id]
        elif operation == "apply_component_dns":
            self.dns[payload["container_id"]] = deepcopy(payload)
            result = {"ok": True}
        elif operation == "read_component_dns":
            result = self.dns[payload["container_id"]]
        else:
            raise AssertionError(operation)
        return self.finish(operation, result)

    def checkpoint(self, event):
        self.events.append(deepcopy(event))


class NetworkAdapterTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory(prefix="routine-n1-")
        self.addCleanup(self.root.cleanup)
        self.plan = environment_policy(environment_profile(), "a" * 64)
        self.plan["bundle_sha256"] = "b" * 64
        self.harness = Harness()
        self.adapter = NetworkAdapter(DockerNetworkTransport(self.harness.docker), NetworkAdminTransport(self.harness.admin),
                                      self.harness.checkpoint, self.root.name, clock=lambda: self.harness.clock)

    def error(self, code, action):
        with self.assertRaises(RoutineError) as caught:
            action()
        self.assertEqual(caught.exception.code, code)

    def prepare(self):
        self.adapter.preflight(self.plan, 30)
        self.adapter.create_networks(self.plan, 30)
        self.adapter.enforce_policy(self.plan, 30)

    def consumer(self, component="worker", container_id="4" * 64):
        entries = self.adapter.component_networks(self.plan, component)
        value = {"Id": container_id, "Config": {"Labels": {"routine.artifact-id": self.plan["artifact_id"],
                 "routine.component": component, "routine.launch-id": "f" * 32}},
                 "HostConfig": {"NetworkMode": entries[0]["network_id"], "PortBindings": {}, "PublishAllPorts": False,
                                "Privileged": False, "CapAdd": [], "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"]},
                 "NetworkSettings": {"Ports": {}, "Networks": {entry["name"]: {"NetworkID": entry["network_id"],
                     "IPAddress": entry["ipv4_address"], "GlobalIPv6Address": "", "LinkLocalIPv6Address": "", "Aliases": [], "Links": [],
                     "MacAddress": "02:00:00:00:00:01", "EndpointID": "7" * 64} for entry in entries}}}
        self.harness.containers[container_id] = value
        return value

    def test_default_refuses_before_any_transport_even_with_enable_flag(self):
        self.plan["activation_enabled"] = True
        self.error("policy_unavailable", lambda: NetworkAdapter().preflight(self.plan, 30))
        self.assertEqual(self.harness.calls, [])

    def test_missing_bootstrap_or_checkpoint_cannot_activate(self):
        for adapter in (NetworkAdapter(docker=self.adapter.docker), NetworkAdapter(docker=self.adapter.docker, admin=self.adapter.admin)):
            self.error("policy_unavailable", lambda: adapter.preflight(self.plan, 30))
        self.assertEqual(self.harness.calls, [])

    def test_plan_cannot_widen_topology_flows_or_activate(self):
        for mutation in (lambda p: p.update(activation_enabled=True), lambda p: p["networks"][0].update(ipv6=True),
                         lambda p: p["firewall"]["flows"].append({"source": "worker", "destination": "public-ipv4", "protocol": "tcp", "port": 443})):
            with self.subTest(mutation=mutation):
                bad = deepcopy(self.plan)
                mutation(bad)
                with self.assertRaises(RoutineError):
                    self.adapter.preflight(bad, 30)
                self.assertEqual(self.harness.calls, [])

    def test_network_create_has_scoped_ipam_nonce_and_no_host_effect_commands(self):
        self.prepare()
        creates = [call for call in self.harness.calls if call[:2] == ("POST", "/networks/create")]
        self.assertEqual(len(creates), 2)
        first, second = creates[0][2], creates[1][2]
        self.assertTrue(first["Internal"])
        self.assertFalse(second["Internal"])
        self.assertFalse(first["EnableIPv6"])
        self.assertEqual(first["IPAM"]["Config"][0]["Subnet"], "172.30.0.0/24")
        self.assertEqual(first["Labels"]["routine.preparation-id"], second["Labels"]["routine.preparation-id"])
        events = [event["event"] for event in self.harness.events]
        self.assertLess(events.index("network-create-intent"), events.index("network-created"))
        self.assertEqual([event["network_id"] for event in self.harness.events if event["event"] == "network-created"], ["1" * 64, "2" * 64])

    def test_attachments_are_fixed_shape_owned_and_only_after_enforcement(self):
        self.adapter.preflight(self.plan, 30)
        self.adapter.create_networks(self.plan, 30)
        self.error("policy_unavailable", lambda: self.adapter.component_networks(self.plan, "worker"))
        self.adapter.enforce_policy(self.plan, 30)
        self.assertEqual(self.adapter.component_networks(self.plan, "worker"), [{"logical_id": "internal", "network_id": "1" * 64,
                         "name": self.plan["networks"][0]["name"], "ipv4_address": "172.30.0.10"}])
        self.assertEqual(len(self.adapter.component_networks(self.plan, "proxy")), 2)
        self.error("invalid_runtime", lambda: self.adapter.component_networks(self.plan, "unknown"))

    def test_existing_network_is_never_adopted_or_deleted(self):
        self.adapter.preflight(self.plan, 30)
        self.harness.collision = True
        self.error("recovery_required", lambda: self.adapter.create_networks(self.plan, 30))
        self.assertFalse(any(call[0] in ("POST", "DELETE") for call in self.harness.calls))

    def test_create_race_wrong_nonce_cannot_be_adopted(self):
        self.adapter.preflight(self.plan, 30)
        def mutate(op, value):
            if op.startswith("/networks/") and op != "/networks/create":
                value["Labels"]["routine.preparation-id"] = "9" * 32
            return value
        self.harness.mutate = mutate
        self.error("recovery_required", lambda: self.adapter.create_networks(self.plan, 30))
        self.error("recovery_required", lambda: self.adapter.create_networks(self.plan, 30))
        self.assertFalse(any(call[0] == "DELETE" for call in self.harness.calls))

    def test_network_configuration_drift_refuses_enforcement(self):
        self.adapter.preflight(self.plan, 30)
        self.adapter.create_networks(self.plan, 30)
        self.harness.networks["1" * 64]["EnableIPv6"] = True
        self.error("recovery_required", lambda: self.adapter.enforce_policy(self.plan, 30))
        self.assertIsNone(self.harness.firewall)

    def test_inventory_missing_identity_or_interlock_blocks(self):
        for key, value in (("daemon_id", "other"), ("boot_id", ""), ("bootstrap_interlock", False),
                           ("bridge_conntrack", False), ("host_addresses", [])):
            with self.subTest(key=key):
                self.setUp()
                def mutate(op, result):
                    if op == "host_inventory":
                        result[key] = value
                    return result
                self.harness.mutate = mutate
                with self.assertRaises(RoutineError):
                    self.adapter.preflight(self.plan, 30)
                self.assertFalse(any(call[0] == "POST" for call in self.harness.calls))

    def test_reservations_cannot_collide_or_trust_a_subnet_for_endpoints(self):
        def mutate(op, value):
            if op == "host_inventory":
                value["allocations"][0]["addresses"]["worker"] = "192.168.1.22"
            return value
        self.harness.mutate = mutate
        self.error("invalid_runtime", lambda: self.adapter.preflight(self.plan, 30))

    def test_initial_firewall_is_executable_nft_json_with_scoped_default_denial(self):
        self.prepare()
        batch = self.harness.firewall
        chains = [command["add"]["chain"] for command in batch["nftables"] if "chain" in command["add"]]
        self.assertIn({"family": "inet", "table": batch["table"], "name": "input", "type": "filter", "hook": "input", "prio": -150, "policy": "accept"}, chains)
        self.assertTrue(any(chain["family"] == "bridge" for chain in chains))
        rules = [command["add"]["rule"] for command in batch["nftables"] if "rule" in command["add"]]
        self.assertTrue(all(rule["expr"][-1] == {"drop": None} for rule in rules))
        self.assertNotIn("flush ruleset", canonical(batch).decode())

    def test_firewall_ack_without_exact_independent_readback_cannot_enforce(self):
        self.adapter.preflight(self.plan, 30)
        self.adapter.create_networks(self.plan, 30)
        self.harness.mutate = lambda op, value: {"ok": True} if op == "read_firewall" else value
        self.error("policy_unavailable", lambda: self.adapter.enforce_policy(self.plan, 30))
        self.error("policy_unavailable", lambda: self.adapter.component_networks(self.plan, "proxy"))
        self.error("recovery_required", lambda: self.adapter.enforce_policy(self.plan, 30))

    def test_endpoint_identity_readback_precedes_dns_and_flow_admission(self):
        self.prepare()
        value = self.consumer()
        self.adapter.verify_component(self.plan, "worker", value, 30)
        operations = [call[0] for call in self.harness.calls]
        self.assertLess(operations.index("prepare_held_component"), operations.index("apply_component_dns"))
        self.assertLess(operations.index("apply_component_dns"), operations.index("read_component_dns"))
        proof = self.adapter.records[self.plan["artifact_id"]]["proofs"]["worker"]
        self.assertTrue(proof["verified"])
        self.assertEqual(proof["container_id"], value["Id"])

    def test_consumer_dns_blocks_embedded_resolver_before_dnat_and_has_no_forwarding(self):
        self.prepare()
        value = self.consumer()
        self.adapter.verify_component(self.plan, "worker", value, 30)
        batch = self.harness.dns[value["Id"]]
        text = canonical(batch).decode()
        self.assertIn('"prio":-300', text)
        self.assertIn("127.0.0.11", text)
        self.assertIn('"udp"', text)
        self.assertIn('"tcp"', text)
        self.assertNotIn("8.8.8.8", batch["resolv_conf"])
        self.assertEqual(batch["hosts"]["database"], "172.30.0.12")
        self.assertTrue(batch["consumer_start_interlocked"])

    def test_service_dns_has_no_names_or_external_resolver(self):
        self.prepare()
        value = self.consumer("service:database")
        self.adapter.verify_component(self.plan, "service:database", value, 30)
        batch = self.harness.dns[value["Id"]]
        self.assertEqual(batch["hosts"], {})
        self.assertNotIn("8.8.8.8", batch["resolv_conf"])

    def test_proxy_dns_is_exact_resolvers_but_embedded_dns_still_denied(self):
        self.prepare()
        self.adapter.start_proxy(self.plan, 30)
        batch = self.harness.dns["3" * 64]
        self.assertEqual(batch["resolv_conf"], "nameserver 8.8.8.8\n")
        self.assertIn("127.0.0.11", canonical(batch).decode())

    def test_missing_namespace_proof_prevents_proxy_start(self):
        self.prepare()
        self.harness.mutate = lambda op, value: {**value, "workload_held": False} if op == "prepare_held_component" else value
        self.error("policy_unavailable", lambda: self.adapter.start_proxy(self.plan, 30))
        self.assertFalse(any(call[0] == "POST" and call[1].endswith("/start") for call in self.harness.calls))
        self.assertIs(self.adapter.stop_proxy(self.plan, 30), True)

    def test_namespace_identity_or_veth_mismatch_fails_closed(self):
        self.prepare()
        value = self.consumer()
        def mutate(op, result):
            if op == "prepare_held_component":
                result["endpoints"][0]["bridge_ifindex"] = 999
            return result
        self.harness.mutate = mutate
        self.error("invalid_runtime", lambda: self.adapter.verify_component(self.plan, "worker", value, 30))
        self.assertEqual(self.harness.dns, {})
        self.error("recovery_required", lambda: self.adapter.verify_component(self.plan, "worker", value, 30))

    def test_dns_effective_readback_drift_holds_consumer(self):
        self.prepare()
        value = self.consumer()
        self.harness.mutate = lambda op, result: {**result, "pre_docker_dns_dnat": False} if op == "read_component_dns" else result
        self.error("policy_unavailable", lambda: self.adapter.verify_component(self.plan, "worker", value, 30))
        self.error("recovery_required", lambda: self.adapter.start_proxy(self.plan, 30))

    def test_unowned_network_endpoint_is_not_trusted_even_in_reserved_subnet(self):
        self.prepare()
        self.harness.networks["1" * 64]["Containers"]["f" * 64] = {"IPv4Address": "172.30.0.15/24", "IPv6Address": ""}
        value = self.consumer()
        self.error("recovery_required", lambda: self.adapter.verify_component(self.plan, "worker", value, 30))

    def test_extra_network_ipv6_aliases_or_host_networking_are_rejected(self):
        mutations = [lambda value: value["HostConfig"].update(NetworkMode="host"),
                     lambda value: value["HostConfig"].update(PortBindings={"22/tcp": [{}]}),
                     lambda value: value["NetworkSettings"]["Networks"].update(extra={}),
                     lambda value: next(iter(value["NetworkSettings"]["Networks"].values())).update(GlobalIPv6Address="::1"),
                     lambda value: next(iter(value["NetworkSettings"]["Networks"].values())).update(Aliases=["other-slice"])]
        self.prepare()
        for mutation in mutations:
            value = deepcopy(self.consumer())
            mutation(value)
            self.error("invalid_runtime", lambda: self.adapter._component_identity(self.plan, "worker", value))

    def test_approved_pair_produces_exact_veth_mac_port_rules_and_reply_state(self):
        self.prepare()
        for component, container_id in (("worker", "4" * 64), ("service:database", "5" * 64)):
            self.adapter.verify_component(self.plan, component, self.consumer(component, container_id), 30)
        text = canonical(self.harness.firewall).decode()
        self.assertIn('"dport"', text)
        self.assertIn("5432", text)
        self.assertIn("172.30.0.10", text)
        self.assertIn("172.30.0.12", text)
        self.assertIn("veth00", text)
        self.assertIn("veth10", text)
        self.assertIn("established", text)
        self.assertNotIn("related", text)

    def test_proxy_public_flow_excludes_host_public_addresses_and_connected_routes(self):
        self.prepare()
        self.adapter.start_proxy(self.plan, 30)
        text = canonical(self.harness.firewall).decode()
        self.assertIn('"addr":"9.9.9.9","len":32', text)
        self.assertIn('"addr":"9.9.9.0","len":24', text)
        self.assertIn('"addr":"169.254.0.0","len":16', text)
        self.assertIn("443", text)
        self.assertIn('"mark"', text)

    def test_proxy_create_bootstrap_start_readiness_stop_uses_only_immutable_id(self):
        self.prepare()
        self.adapter.start_proxy(self.plan, 30)
        self.adapter.wait_proxy_ready(self.plan, 30)
        self.assertIs(self.adapter.stop_proxy(self.plan, 30), True)
        start = next(index for index, call in enumerate(self.harness.calls) if call[0] == "POST" and call[1].endswith("/start"))
        dns = next(index for index, call in enumerate(self.harness.calls) if call[0] == "read_component_dns")
        self.assertLess(dns, start)
        lifecycle = [call[1] for call in self.harness.calls if call[0] == "POST" and (call[1].endswith("/start") or "/stop?" in call[1])]
        self.assertEqual(lifecycle, ["/containers/" + "3" * 64 + "/start", "/containers/" + "3" * 64 + "/stop?t=5"])
        self.assertFalse(any(call[0] == "DELETE" for call in self.harness.calls))
        from pathlib import Path
        self.assertTrue(any(Path(self.root.name).rglob("proxy.json")))
        self.assertTrue(self.harness.networks)
        self.assertIsNotNone(self.harness.firewall)
        self.assertFalse(next(event for event in self.harness.events if event["event"] == "proxy-ready")["qualified"])

    def test_existing_proxy_is_not_replaced_started_or_stopped(self):
        self.prepare()
        self.harness.collision = True
        self.error("recovery_required", lambda: self.adapter.start_proxy(self.plan, 30))
        self.error("recovery_required", lambda: self.adapter.stop_proxy(self.plan, 30))
        self.assertFalse(any(call[0] == "POST" and call[1].startswith("/containers/") for call in self.harness.calls))

    def test_proxy_replacement_is_not_stopped(self):
        self.prepare()
        self.adapter.start_proxy(self.plan, 30)
        self.harness.containers["3" * 64]["Id"] = "f" * 64
        self.error("recovery_required", lambda: self.adapter.stop_proxy(self.plan, 30))
        self.assertFalse(any(call[0] == "POST" and "/stop?" in call[1] for call in self.harness.calls))

    def test_proxy_start_ambiguity_can_only_stop_known_created_id(self):
        self.prepare()
        def mutate(op, result):
            if op.endswith("/start"):
                raise OSError("private diagnostic canary")
            return result
        self.harness.mutate = mutate
        self.error("adapter_failed", lambda: self.adapter.start_proxy(self.plan, 30))
        self.harness.mutate = None
        self.assertIs(self.adapter.stop_proxy(self.plan, 30), True)
        self.error("recovery_required", lambda: self.adapter.start_proxy(self.plan, 30))
        self.assertNotIn("private diagnostic", canonical(self.harness.events).decode())

    def test_unknown_creation_identity_is_held_not_guessed_from_name(self):
        self.prepare()
        self.harness.mutate = lambda op, result: {"Warnings": []} if op.startswith("/containers/create?") else result
        with self.assertRaises(RoutineError):
            self.adapter.start_proxy(self.plan, 30)
        self.error("recovery_required", lambda: self.adapter.stop_proxy(self.plan, 30))
        self.assertFalse(any(call[0] == "POST" and "/stop?" in call[1] for call in self.harness.calls))

    def test_unconfirmed_stop_does_not_return_true_or_remove_artifacts(self):
        self.prepare()
        self.adapter.start_proxy(self.plan, 30)
        self.harness.mutate = lambda op, value: {**value, "State": {"Running": True}} if op.endswith("/json") and op.startswith("/containers/") else value
        self.error("stop_unconfirmed", lambda: self.adapter.stop_proxy(self.plan, 30))
        self.assertFalse(any(call[0] == "DELETE" for call in self.harness.calls))

    def test_proxy_policy_effective_config_and_health_drift_prevents_readiness(self):
        self.prepare()
        self.adapter.start_proxy(self.plan, 30)
        self.harness.containers["3" * 64]["Config"]["Healthcheck"]["Test"] = ["CMD", "true"]
        self.error("invalid_runtime", lambda: self.adapter.wait_proxy_ready(self.plan, 30))

    def test_namespace_replacement_after_start_prevents_readiness(self):
        self.prepare()
        self.adapter.start_proxy(self.plan, 30)
        self.harness.identities["3" * 64]["namespace_inode"] += 1
        self.error("recovery_required", lambda: self.adapter.wait_proxy_ready(self.plan, 30))

    def test_plan_drift_prevents_every_lifecycle_operation(self):
        self.prepare()
        self.plan["resources"]["pids"] += 1
        for action in (lambda: self.adapter.create_networks(self.plan, 30), lambda: self.adapter.enforce_policy(self.plan, 30),
                       lambda: self.adapter.component_networks(self.plan, "worker"), lambda: self.adapter.stop_proxy(self.plan, 30)):
            self.error("recovery_required", action)

    def test_late_transport_success_cannot_be_admitted(self):
        def mutate(op, result):
            if op == "/info":
                self.harness.clock += 31
            return result
        self.harness.mutate = mutate
        self.error("command_timeout", lambda: self.adapter.preflight(self.plan, 30))
        self.assertEqual(len(self.harness.calls), 1)
        self.error("recovery_required", lambda: self.adapter.create_networks(self.plan, 30))

    def test_deadlines_are_shared_across_network_transaction_calls(self):
        self.adapter.preflight(self.plan, 30)
        def mutate(op, result):
            self.harness.clock += 6
            return result
        self.harness.mutate = mutate
        self.error("command_timeout", lambda: self.adapter.create_networks(self.plan, 30))
        timeouts = [call[-1] for call in self.harness.calls[2:]]
        self.assertEqual(timeouts, [30, 24, 18, 12, 6])

    def test_checkpoint_failure_before_effect_does_not_create(self):
        self.adapter.preflight(self.plan, 30)
        def fail(event):
            raise OSError("checkpoint failed")
        self.adapter.checkpoint = fail
        with self.assertRaises(OSError):
            self.adapter.create_networks(self.plan, 30)
        self.assertFalse(any(call[0] == "POST" for call in self.harness.calls))

    def test_creation_identity_checkpoint_failure_keeps_id_for_explicit_stop(self):
        self.prepare()
        def checkpoint(event):
            if event["event"] == "proxy-created":
                raise OSError("journal failed")
            self.harness.checkpoint(event)
        self.adapter.checkpoint = checkpoint
        with self.assertRaises(OSError):
            self.adapter.start_proxy(self.plan, 30)
        self.assertFalse(any(call[0] == "POST" and call[1].endswith("/start") for call in self.harness.calls))
        self.adapter.checkpoint = self.harness.checkpoint
        self.assertIs(self.adapter.stop_proxy(self.plan, 30), True)

    def test_network_healthcheck_has_no_loopback_only_interface_assumption(self):
        check = healthcheck("a" * 64, "b" * 64)
        self.assertNotIn("set(os.listdir", check[5])
        self.assertIn("GET / HTTP/1.1", check[5])
        self.assertIn("assets=", check[5])

    def test_hook_order_is_required_not_inferred_from_backend_name(self):
        def mutate(op, result):
            if op == "host_inventory":
                result["hook_priorities"]["docker_accept"] = -300
            return result
        self.harness.mutate = mutate
        self.error("policy_unavailable", lambda: self.adapter.preflight(self.plan, 30))
        self.assertFalse(any(call[0] == "POST" for call in self.harness.calls))

    def test_changed_host_routes_blocks_consumer_before_bootstrap(self):
        self.prepare()
        value = self.consumer()
        self.harness.host_identity["connected_routes"].append("8.8.8.0/24")
        self.error("recovery_required", lambda: self.adapter.verify_component(self.plan, "worker", value, 30))
        self.assertFalse(any(call[0] == "prepare_held_component" for call in self.harness.calls))

    def test_exposed_but_unpublished_service_port_is_not_a_host_publish(self):
        self.prepare()
        value = self.consumer("service:database")
        value["NetworkSettings"]["Ports"] = {"5432/tcp": None}
        self.adapter.verify_component(self.plan, "service:database", value, 30)
        value["NetworkSettings"]["Ports"]["5432/tcp"] = [{"HostIp": "0.0.0.0", "HostPort": "5432"}]
        self.error("invalid_runtime", lambda: self.adapter._component_identity(self.plan, "service:database", value))

    def test_rule_batches_bind_numeric_interface_ids_not_just_names_or_addresses(self):
        self.prepare()
        self.adapter.start_proxy(self.plan, 30)
        text = canonical(self.harness.firewall).decode()
        self.assertIn('"key":"iif"', text)
        self.assertIn('"key":"oif"', text)
        self.assertIn('"chain":"input","expr":[{"match":{"left":{"meta":{"key":"iifname"}},"op":"==","right":"veth', text)
        self.assertTrue(any(command["add"].get("chain", {}).get("hook") == "output" for command in self.harness.firewall["nftables"]))

    def test_readiness_polls_starting_inside_one_shared_deadline(self):
        self.prepare()
        self.adapter.start_proxy(self.plan, 30)
        inspections = [0]
        def mutate(op, value):
            if op.startswith("/containers/") and op.endswith("/json"):
                inspections[0] += 1
                if inspections[0] == 1:
                    value["State"]["Health"]["Status"] = "starting"
            return value
        self.harness.mutate = mutate
        self.adapter.sleep = lambda delay: setattr(self.harness, "clock", self.harness.clock + delay)
        self.adapter.wait_proxy_ready(self.plan, 30)
        self.assertEqual(inspections[0], 2)
        self.assertGreater(self.harness.clock, 0)

    def test_retained_policy_replacement_is_not_adopted_even_with_identical_bytes(self):
        self.prepare()
        self.adapter.start_proxy(self.plan, 30)
        path = self.adapter.records[self.plan["artifact_id"]]["proxy"]["path"]
        replacement = path.with_suffix(".replacement")
        replacement.write_bytes(path.read_bytes())
        replacement.chmod(0o444)
        replacement.replace(path)
        self.error("unsafe_state", lambda: self.adapter.wait_proxy_ready(self.plan, 30))

    def test_private_helper_diagnostics_do_not_enter_endpoint_checkpoints(self):
        self.prepare()
        value = self.consumer()
        def mutate(op, result):
            if op == "prepare_held_component":
                result["endpoints"][0]["diagnostic"] = "private-output-canary"
            return result
        self.harness.mutate = mutate
        self.adapter.verify_component(self.plan, "worker", value, 30)
        self.assertNotIn("private-output-canary", canonical(self.harness.events).decode())

    def test_distinct_components_cannot_share_a_host_interface_identity(self):
        self.prepare()
        self.adapter.verify_component(self.plan, "worker", self.consumer(), 30)
        value = self.consumer("service:database", "5" * 64)
        def mutate(op, result):
            if op == "prepare_held_component":
                result["endpoints"][0]["host_veth"] = "veth00"
            return result
        self.harness.mutate = mutate
        self.error("invalid_runtime", lambda: self.adapter.verify_component(self.plan, "service:database", value, 30))

    def test_nonfinite_deadlines_fail_before_transport(self):
        for timeout in (0, -1, True, float("inf"), float("nan")):
            self.error("command_timeout", lambda: self.adapter.preflight(self.plan, timeout))
        self.assertEqual(self.harness.calls, [])


if __name__ == "__main__":
    unittest.main()
