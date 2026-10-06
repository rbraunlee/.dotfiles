"""N1 network/proxy adapter. Injectable offline implementation, not admission.

There is no production executor or enable flag. A separately approved trusted
bootstrap helper is required even when Docker and firewall transports are injected.
All ownership is per adapter instance; restart/reconciliation belongs to the host.
"""
from copy import deepcopy
import ipaddress
import re
import time
from urllib.parse import urlencode
import uuid

from .contracts import canonical, digest, hash_value, require
from .network_transport import Budget, DockerNetworkTransport, NetworkAdminTransport, fingerprint
from .network_firewall import dns_batch, firewall_batch, interface
from .network_proxy import ProxyLifecycle


class NetworkAdapter:
    def __init__(self, docker=None, admin=None, checkpoint=None, artifact_root=None, clock=time.monotonic, sleep=time.sleep):
        self.docker = docker or DockerNetworkTransport()
        self.admin = admin or NetworkAdminTransport()
        self.checkpoint = checkpoint
        self.clock = clock
        self.sleep = sleep
        self.records = {}
        self.proxy = ProxyLifecycle(self, artifact_root)

    def _event(self, record, event, **values):
        # Callback must synchronously durably journal before returning. Creation
        # identities are kept locally *before* callback, so failure still permits
        # an explicit stop of an already-owned proxy; no automatic retry/adoption.
        require(self.checkpoint is not None, "policy_unavailable", "An ownership checkpoint sink is required")
        self.checkpoint(deepcopy({"event": event, "artifact_id": record["plan"]["artifact_id"],
                                  "plan_sha256": record["plan_sha256"], "preparation_id": record["nonce"],
                                  **values}))

    def _record(self, plan):
        require(isinstance(plan, dict), "invalid_runtime", "Expected an immutable environment plan")
        record = self.records.get(plan.get("artifact_id"))
        require(record is not None and record["plan_sha256"] == fingerprint(plan),
                "recovery_required", "Network plan has not been admitted or has changed")
        return record

    def _docker(self, budget, method, path, body=None):
        return budget.call(self.docker.call, method, path, body)

    def _admin(self, budget, operation, payload):
        return budget.call(self.admin.call, operation, payload)

    def preflight(self, plan, timeout):
        budget = Budget(timeout, self.clock)
        require(self.docker.request is not None and self.admin.exchange is not None and self.checkpoint is not None,
                "policy_unavailable", "Networking/bootstrap execution is not configured or qualified")
        require(isinstance(plan, dict), "invalid_runtime", "Expected an environment plan")
        artifact = plan.get("artifact_id")
        hash_value(artifact)
        require(artifact not in self.records, "recovery_required", "A previous preparation cannot be adopted or retried")
        require(plan.get("activation_enabled") is False and plan.get("version") == 1,
                "policy_unavailable", "A plan cannot enable production networking")
        networks, components = plan.get("networks"), plan.get("components")
        require(isinstance(components, list) and len(set(components)) == len(components) and
                all(value == "proxy" or isinstance(value, str) and re.fullmatch(r"service:[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value) for value in components),
                "invalid_runtime", "Malformed network components")
        members = ["worker"] + components
        expected = [{"id": "internal", "name": "routine-" + artifact[:24] + "-internal", "internal": True,
                     "ipv6": False, "members": members}]
        if "proxy" in components:
            expected.append({"id": "egress", "name": "routine-" + artifact[:24] + "-egress", "internal": False,
                             "ipv6": False, "members": ["proxy"]})
        require(networks == expected, "invalid_runtime", "Network topology differs from the fixed isolated topology")
        firewall = plan.get("firewall", {})
        require(firewall.get("default") == "deny" and firewall.get("ipv6") == "deny" and
                firewall.get("host_lan") == "deny" and firewall.get("cross_environment") == "deny" and
                firewall.get("enforcement_points") == ["host-input", "host-forward-before-docker-accept", "same-bridge", "container-dns"],
                "invalid_runtime", "Required enforcement points are missing")
        flows = firewall.get("flows")
        require(isinstance(flows, list), "invalid_runtime", "Malformed explicit flows")
        servers = sorted({flow["destination"] for flow in flows if isinstance(flow, dict) and flow.get("port") == 53})
        from .policy import public_ipv4
        require(all(public_ipv4(server) for server in servers), "invalid_runtime", "DNS requires approved public IPv4 resolvers")
        expected_flows = []
        if "proxy" in components:
            expected_flows += [{"source": "worker", "destination": "proxy", "protocol": "tcp", "port": 3128},
                               {"source": "proxy", "destination": "public-ipv4", "protocol": "tcp", "port": 443}]
            expected_flows += [{"source": "proxy", "destination": server, "protocol": protocol, "port": 53}
                               for server in servers for protocol in ("udp", "tcp")]
            require(servers and plan.get("proxy_policy"), "invalid_runtime", "Proxy policy and explicit DNS are required")
        services = plan.get("services")
        require(isinstance(services, list) and ["service:" + entry["id"] for entry in services] == [value for value in components if value != "proxy"],
                "invalid_runtime", "Service identities differ from network membership")
        for service in services:
            expected_flows += [{"source": "worker", "destination": "service:" + service["id"], "protocol": "tcp", "port": port}
                               for port in service["ports"]]
        require(sorted(map(canonical, flows)) == sorted(map(canonical, expected_flows)),
                "invalid_runtime", "Unsupported or widened firewall flow")
        record = {"plan": deepcopy(plan), "plan_sha256": fingerprint(plan), "nonce": uuid.uuid4().hex,
                  "networks": {}, "bindings": {}, "proofs": {}, "enforced": False, "creation_attempted": False}
        self.records[artifact] = record  # An interrupted preflight is not retryable.
        info = self._docker(budget, "GET", "/info")
        require(isinstance(info, dict) and isinstance(info.get("ID"), str) and info["ID"],
                "invalid_runtime", "Missing immutable daemon identity")
        inventory = self._admin(budget, "host_inventory", {"artifact_id": artifact, "daemon_id": info["ID"], "networks": networks})
        self._inventory(inventory, info["ID"], networks)
        inventory["dns_servers"] = servers
        record["inventory"] = deepcopy(inventory)
        self._event(record, "network-preflight", daemon_id=info["ID"], observation_id=inventory["observation_id"])
        budget.remaining()
        record["preflight_complete"] = True

    @staticmethod
    def _inventory(value, daemon_id, networks):
        require(isinstance(value, dict) and value.get("daemon_id") == daemon_id and value.get("backend") == "nftables-json" and
                value.get("bootstrap_interlock") is True and value.get("bridge_conntrack") is True and
                value.get("enforcement_points") == ["host-input", "host-forward-before-docker-accept", "same-bridge", "container-dns"],
                "policy_unavailable", "Trusted host/bootstrap capabilities are not established")
        require(value.get("hook_priorities") == {"conntrack": -200, "routine_filter": -150, "docker_accept": 0,
                                                "dns_output": -300, "docker_dns_dnat": -100},
                "policy_unavailable", "Conntrack/Docker/DNS hook ordering is not positively observed")
        require(isinstance(value.get("boot_id"), str) and re.fullmatch(r"[0-9a-f-]{36}", value["boot_id"]),
                "invalid_runtime", "Missing host boot identity")
        hash_value(value.get("observation_id"))
        require(isinstance(value.get("host_addresses"), list) and value["host_addresses"] and
                isinstance(value.get("connected_routes"), list) and value["connected_routes"],
                "invalid_runtime", "Host addresses and connected routes must be positively observed")
        from .network_firewall import exclusions
        try:
            exclusions(value)
            allocations = value.get("allocations")
            require(isinstance(allocations, list) and len(allocations) == len(networks), "invalid_runtime", "Missing trusted network reservations")
            subnets, bridges = [], []
            for expected, allocation in zip(networks, allocations):
                require(allocation.get("logical_id") == expected["id"], "invalid_runtime", "Network reservation order differs")
                subnet = ipaddress.IPv4Network(allocation["subnet"], strict=True)
                gateway = ipaddress.IPv4Address(allocation["gateway"])
                require(subnet.is_private and 24 <= subnet.prefixlen <= 27 and gateway in subnet and
                        gateway not in (subnet.network_address, subnet.broadcast_address),
                        "invalid_runtime", "Invalid bounded private IPAM reservation")
                require(not any(subnet.overlaps(other) for other in subnets) and
                        not any(subnet.overlaps(ipaddress.IPv4Network(route)) for route in value["connected_routes"]),
                        "invalid_runtime", "Network reservations collide with observed routes")
                addresses = allocation.get("addresses", {})
                require(set(addresses) == set(expected["members"]) and len(set(addresses.values())) == len(addresses),
                        "invalid_runtime", "Endpoint reservations must be exact and distinct")
                require(all(ipaddress.IPv4Address(address) in subnet and ipaddress.IPv4Address(address) not in
                            (gateway, subnet.network_address, subnet.broadcast_address) for address in addresses.values()),
                        "invalid_runtime", "Endpoint address is outside the owned reservation")
                subnets.append(subnet)
                bridges.append(interface(allocation["bridge"]))
            require(len(set(bridges)) == len(bridges), "invalid_runtime", "Bridge identities must be distinct")
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            from .contracts import RoutineError
            raise RoutineError("invalid_runtime", "Malformed trusted network inventory") from exc

    def create_networks(self, plan, timeout):
        budget, record = Budget(timeout, self.clock), self._record(plan)
        require(record.get("preflight_complete") is True and not record["creation_attempted"],
                "recovery_required", "Network creation requires completed preflight and cannot be retried")
        for expected, allocation in zip(plan["networks"], record["inventory"]["allocations"]):
            path = "/networks?" + urlencode({"filters": canonical({"name": [expected["name"]]}).decode()})
            rows = self._docker(budget, "GET", path)
            require(rows == [], "recovery_required", "An existing network cannot be adopted, replaced or removed")
            body = {"Name": expected["name"], "CheckDuplicate": True, "Driver": "bridge", "Internal": expected["internal"],
                    "EnableIPv6": False, "Attachable": False,
                    "IPAM": {"Driver": "default", "Config": [{"Subnet": allocation["subnet"], "Gateway": allocation["gateway"]}]},
                    "Options": {"com.docker.network.bridge.name": allocation["bridge"], "com.docker.network.bridge.enable_icc": "true"},
                    "Labels": {"routine.artifact-id": plan["artifact_id"], "routine.network-id": expected["id"],
                               "routine.preparation-id": record["nonce"]}}
            self._event(record, "network-create-intent", logical_id=expected["id"], transaction=body)
            record["creation_attempted"] = True
            created = self._docker(budget, "POST", "/networks/create", body)
            require(isinstance(created, dict) and not created.get("Warning"), "invalid_runtime", "Network creation returned ambiguous metadata")
            network_id = created.get("Id")
            hash_value(network_id)
            owned = {**deepcopy(allocation), "network_id": network_id, "name": expected["name"], "create_body": body}
            record["networks"][expected["id"]] = owned
            self._verify_network(record, owned, self._docker(budget, "GET", "/networks/" + network_id), empty=True)
            proof = self._admin(budget, "observe_network", {"network_id": network_id, "bridge": allocation["bridge"],
                                                          "boot_id": record["inventory"]["boot_id"]})
            require(isinstance(proof, dict) and proof.get("network_id") == network_id and proof.get("bridge") == allocation["bridge"] and
                    proof.get("boot_id") == record["inventory"]["boot_id"] and type(proof.get("bridge_ifindex")) is int and proof["bridge_ifindex"] > 0,
                    "invalid_runtime", "Bridge identity is not positively observed")
            owned["bridge_ifindex"] = proof["bridge_ifindex"]
            self._event(record, "network-created", logical_id=expected["id"], network_id=network_id,
                        bridge=owned["bridge"], bridge_ifindex=owned["bridge_ifindex"])
            budget.remaining()

    @staticmethod
    def _verify_network(record, expected, value, empty=False):
        body = expected["create_body"]
        require(isinstance(value, dict) and value.get("Id") == expected["network_id"] and
                all(value.get(key) == body[key] for key in ("Name", "Driver", "Internal", "EnableIPv6", "Attachable", "IPAM", "Options", "Labels")) and
                isinstance(value.get("Containers"), dict) and (not empty or not value["Containers"]),
                "recovery_required", "Network ownership or effective topology changed")
        for container_id, endpoint in value["Containers"].items():
            known = next((proof for proof in record["proofs"].values() if proof["container_id"] == container_id), None)
            require(known is not None and isinstance(endpoint, dict), "recovery_required", "An unowned endpoint joined a routine network")
            address = expected["addresses"].get(known["component"])
            require(endpoint.get("IPv4Address", "").split("/")[0] == address and not endpoint.get("IPv6Address"),
                    "recovery_required", "Network endpoint addresses changed")

    def _apply_firewall(self, record, budget):
        transaction = firewall_batch(record["plan"], record["inventory"], record["networks"], record["bindings"])
        self._event(record, "firewall-intent", transaction=transaction)
        self._admin(budget, "apply_firewall", transaction)
        readback = self._admin(budget, "read_firewall", {"owner": record["plan"]["artifact_id"]})
        require(readback == transaction, "policy_unavailable", "Effective firewall readback differs from the owned transaction")
        record["firewall"] = transaction
        self._event(record, "firewall-verified", transaction_sha256=fingerprint(transaction))

    def enforce_policy(self, plan, timeout):
        budget, record = Budget(timeout, self.clock), self._record(plan)
        require(set(record["networks"]) == {entry["id"] for entry in plan["networks"]} and not record.get("enforcement_attempted"),
                "recovery_required", "Policy needs exactly this preparation's complete network creation")
        record["enforcement_attempted"] = True
        for network in record["networks"].values():
            self._verify_network(record, network, self._docker(budget, "GET", "/networks/" + network["network_id"]), empty=True)
        self._apply_firewall(record, budget)
        record["enforced"] = True

    def component_networks(self, plan, component):
        record = self._record(plan)
        require(record["enforced"], "policy_unavailable", "Attachments are unavailable before verified default-deny enforcement")
        require(component == "worker" or component in plan["components"], "invalid_runtime", "Unknown network consumer")
        return [{"logical_id": logical, "network_id": value["network_id"], "name": value["name"],
                 "ipv4_address": value["addresses"][component]}
                for logical, value in record["networks"].items() if component in value["addresses"]]

    def _component_identity(self, plan, component, value):
        expected = self.component_networks(plan, component)
        require(isinstance(value, dict), "invalid_runtime", "Expected a container inspection")
        container_id = value.get("Id")
        hash_value(container_id)
        config, host, settings = value.get("Config", {}), value.get("HostConfig", {}), value.get("NetworkSettings", {})
        require(all(isinstance(section, dict) for section in (config, host, settings)),
                "invalid_runtime", "Malformed consumer configuration sections")
        labels = config.get("Labels", {})
        require(isinstance(labels, dict) and isinstance(host.get("SecurityOpt"), list),
                "invalid_runtime", "Malformed consumer labels or security options")
        require(labels.get("routine.artifact-id") == plan["artifact_id"] and
                labels.get("routine.component") == component and isinstance(labels.get("routine.launch-id"), str) and
                re.fullmatch(r"[0-9a-f]{32}", labels["routine.launch-id"]),
                "recovery_required", "Consumer ownership labels are missing")
        require(host.get("NetworkMode") in {entry["name"] for entry in expected} | {entry["network_id"] for entry in expected} and
                not host.get("PortBindings") and host.get("PublishAllPorts") is False and host.get("Privileged") is False and
                not host.get("CapAdd") and host.get("CapDrop") == ["ALL"] and host.get("ExtraHosts") in (None, []) and
                any(option in ("no-new-privileges", "no-new-privileges:true") for option in host.get("SecurityOpt", [])),
                "invalid_runtime", "Consumer network privileges differ from policy")
        attached = settings.get("Networks")
        ports = settings.get("Ports")
        require(isinstance(attached, dict) and set(attached) == {entry["name"] for entry in expected} and
                (ports is None or isinstance(ports, dict) and all(value is None for value in ports.values())),
                "invalid_runtime", "Consumer has missing/extra networks or published ports")
        for entry in expected:
            actual = attached[entry["name"]]
            require(isinstance(actual, dict), "invalid_runtime", "Malformed consumer endpoint")
            aliases = actual.get("Aliases")
            allowed_aliases = set()
            if component.startswith("service:"):
                # Compose's fixed generated aliases are not caller attachment
                # metadata. Match the service adapter's deterministic identity.
                component_hash = digest(component.encode())
                allowed_aliases = {"service-" + component_hash[:24],
                                   "routine-service-" + plan["artifact_id"][:24] + "-" + component_hash[:16],
                                   container_id, container_id[:12]}
            aliases_valid = aliases in (None, []) or (isinstance(aliases, list) and
                            all(isinstance(alias, str) and alias in allowed_aliases for alias in aliases))
            require(isinstance(actual, dict) and actual.get("NetworkID") == entry["network_id"] and
                    actual.get("IPAddress") == entry["ipv4_address"] and not actual.get("GlobalIPv6Address") and
                    not actual.get("LinkLocalIPv6Address") and aliases_valid and actual.get("Links") in (None, []) and
                    re.fullmatch(r"[0-9a-f]{64}", actual.get("EndpointID", "")) and
                    re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", actual.get("MacAddress", "")),
                    "invalid_runtime", "Consumer endpoint identity differs from the owned attachment")
        return container_id, expected

    def verify_component(self, plan, component, container_inspect, timeout):
        record = self._record(plan)
        require(not record.get("failed_components"), "recovery_required", "Failed namespace admission requires deliberate recovery")
        try:
            return self._verify_component(plan, component, container_inspect, timeout)
        except BaseException:
            record.setdefault("failed_components", set()).add(component)
            raise

    def _verify_component(self, plan, component, container_inspect, timeout):
        budget, record = Budget(timeout, self.clock), self._record(plan)
        stable = {key: record["inventory"][key] for key in ("daemon_id", "boot_id", "observation_id", "host_addresses", "connected_routes", "hook_priorities")}
        require(self._admin(budget, "read_host_identity", {"owner": plan["artifact_id"]}) == stable,
                "recovery_required", "Host addresses/routes/runtime/hook identity changed")
        container_id, expected = self._component_identity(plan, component, container_inspect)
        prior = record["proofs"].get(component)
        if prior:
            require(prior["container_id"] == container_id and prior["launch_id"] == container_inspect["Config"]["Labels"]["routine.launch-id"],
                    "recovery_required", "Consumer identity was replaced")
        self._event(record, "bootstrap-intent", component=component, container_id=container_id, attachments=expected)
        operation = "observe_component" if prior else "prepare_held_component"
        proof = self._admin(budget, operation, {"owner": plan["artifact_id"], "component": component,
                            "container_id": container_id, "attachments": expected, "boot_id": record["inventory"]["boot_id"]})
        require(isinstance(proof, dict) and proof.get("container_id") == container_id and
                proof.get("boot_id") == record["inventory"]["boot_id"] and type(proof.get("namespace_inode")) is int and proof["namespace_inode"] > 0 and
                type(proof.get("namespace_device")) is int and proof["namespace_device"] > 0 and
                proof.get("consumer_start_interlocked") is True and proof.get("survives_consumer_start") is True and
                (prior is not None or proof.get("workload_held") is True),
                "policy_unavailable", "Trusted pre-consumer namespace identity/interlock is missing")
        identity = {key: proof[key] for key in ("boot_id", "namespace_inode", "namespace_device")}
        require(prior is None or prior["identity"] == identity, "recovery_required", "Consumer namespace changed across start")
        endpoints = proof.get("endpoints")
        require(isinstance(endpoints, list) and len(endpoints) == len(expected), "invalid_runtime", "Missing observed interface identities")
        for entry, endpoint in zip(expected, endpoints):
            require(isinstance(endpoint, dict), "invalid_runtime", "Malformed observed endpoint")
            network = record["networks"][entry["logical_id"]]
            actual = container_inspect["NetworkSettings"]["Networks"][entry["name"]]
            require(all(endpoint.get(key) == entry[key] for key in ("logical_id", "network_id", "ipv4_address")) and
                    endpoint.get("bridge_ifindex") == network["bridge_ifindex"] and endpoint.get("mac") == actual["MacAddress"] and
                    type(endpoint.get("host_ifindex")) is int and endpoint["host_ifindex"] > 0 and
                    type(endpoint.get("container_ifindex")) is int and endpoint["container_ifindex"] > 0,
                    "invalid_runtime", "Endpoint/interface identities are not positively bound")
            interface(endpoint.get("host_veth"))
        # Only allowlisted identity metadata may reach checkpoints or transactions.
        keys = ("logical_id", "network_id", "ipv4_address", "bridge_ifindex", "host_ifindex", "container_ifindex", "host_veth", "mac")
        endpoints = [{key: endpoint[key] for key in keys} for endpoint in endpoints]
        other_endpoints = [entry for name, entries in record["bindings"].items() if name != component for entry in entries]
        require(len({entry["host_veth"] for entry in endpoints}) == len(endpoints) and
                len({entry["host_ifindex"] for entry in endpoints}) == len(endpoints) and
                not any(entry["host_veth"] == other["host_veth"] or entry["host_ifindex"] == other["host_ifindex"]
                        for entry in endpoints for other in other_endpoints),
                "invalid_runtime", "Host interface identity is shared by distinct consumers")
        require(prior is None or record["bindings"][component] == endpoints, "recovery_required", "Consumer interface identity changed")
        # Pin ID before reading networks: the new endpoint may now appear in their
        # Containers maps, but no other unowned endpoint may be admitted.
        record["proofs"][component] = {"container_id": container_id, "component": component, "identity": identity,
                                       "launch_id": container_inspect["Config"]["Labels"]["routine.launch-id"]}
        record["bindings"][component] = deepcopy(endpoints)
        for network in record["networks"].values():
            self._verify_network(record, network, self._docker(budget, "GET", "/networks/" + network["network_id"]))
        transaction = dns_batch(plan, component, container_id, identity,
                                {name: self.component_networks(plan, name) for name in ["worker"] + plan["components"]})
        self._event(record, "dns-intent", component=component, container_id=container_id, transaction=transaction)
        self._admin(budget, "apply_component_dns", transaction)
        require(self._admin(budget, "read_component_dns", {"container_id": container_id, "identity": identity}) == transaction,
                "policy_unavailable", "Namespace rules/files or pre-DNAT DNS readback differs")
        self._apply_firewall(record, budget)
        record["proofs"][component]["verified"] = True
        self._event(record, "component-network-verified", component=component, container_id=container_id,
                    namespace_identity=identity, endpoints=endpoints, dns_sha256=fingerprint(transaction))
        budget.remaining()

    def start_proxy(self, plan, timeout):
        return self.proxy.start(plan, timeout)

    def wait_proxy_ready(self, plan, timeout):
        return self.proxy.ready(plan, timeout)

    def stop_proxy(self, plan, timeout):
        return self.proxy.stop(plan, timeout)
