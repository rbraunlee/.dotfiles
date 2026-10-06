"""Declarative M2 network/service/credential policy. Not an installed firewall."""
import ipaddress
from pathlib import PurePosixPath
import re

from .contracts import canonical, command, fields, hash_value, identifier, positive, require, resource_limits, sequence, validate_profile


# Conservative IPv4 exclusions shared in meaning with the container proxy. Never
# let differences in Python's IANA tables widen the future host DNS/egress policy.
EXCLUDED_V4 = tuple(ipaddress.ip_network(value) for value in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16",
    "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4"))


def public_ipv4(value):
    try:
        address = ipaddress.IPv4Address(value) if isinstance(value, str) else None
    except ValueError:
        return False
    return bool(address and str(address) == value and address.is_global and
                not any(address in network for network in EXCLUDED_V4))


def validate_environment_profile(profile):
    network, budgets = profile["network"], profile["budgets"]
    require(len(canonical({"allowed_domains": network["allowed_domains"], **network["proxy"]})) <= 65536,
            "invalid_profile", "Proxy policy exceeds its 64 KiB component limit")
    servers = sequence(network["dns_servers"], "DNS servers")
    require(all(public_ipv4(server) for server in servers) and len(servers) == len(set(servers)),
            "invalid_profile", "DNS servers must be distinct public native IPv4 addresses")
    require(bool(servers) == bool(network["allowed_domains"]), "invalid_profile", "Egress requires explicit DNS servers; offline profiles cannot grant DNS egress")
    for service in profile["services"]:
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", service["image"]), "invalid_profile", "Services require pinned local image IDs")
        require(isinstance(service["user"], str) and re.fullmatch(r"[1-9][0-9]{0,8}:[1-9][0-9]{0,8}", service["user"]),
                "invalid_profile", "Services require an explicit non-root numeric UID:GID")
        ports = sequence(service["ports"], "service ports", nonempty=True)
        require(all(type(port) is int and 1 <= port <= 65535 for port in ports) and len(ports) == len(set(ports)),
                "invalid_profile", "Service ports must be distinct TCP ports")
        resource_limits(service["resources"])
        require(service["resources"]["command_seconds"] <= budgets["slice_seconds"], "invalid_profile", "Service command budget exceeds slice runtime")
        command(service["readiness"], service["resources"]["command_seconds"])
        targets = []
        total = 0
        for mount in sequence(service["tmpfs"], "service tmpfs"):
            fields(mount, ("target", "size_mb"), "service tmpfs")
            require(isinstance(mount["target"], str) and "\0" not in mount["target"] and "\\" not in mount["target"],
                    "invalid_profile", "Expected normalized tmpfs target")
            target = PurePosixPath(mount["target"])
            forbidden = ("/run/credentials", "/proc", "/sys", "/dev", "/etc", "/opt", "/control")
            require(target.is_absolute() and str(target) == mount["target"] and ".." not in target.parts and
                    target != PurePosixPath("/") and not any(target.is_relative_to(path) or PurePosixPath(path).is_relative_to(target) for path in forbidden) and
                    not any(target.is_relative_to(path) or path.is_relative_to(target) for path in targets),
                    "invalid_profile", "Unsafe or overlapping service tmpfs target")
            positive(mount["size_mb"], "service tmpfs size")
            total += mount["size_mb"]
            targets.append(target)
        require(total <= service["resources"]["disk_mb"], "invalid_profile", "Service tmpfs exceeds its approved disk budget")
    consumers = {"service:" + service["id"]: "development" for service in profile["services"]}
    expected_providers = set()
    for provider in profile["providers"]:
        domains = sequence(provider["domains"], "provider domains", nonempty=True)
        require(all(isinstance(domain, str) and domain in network["allowed_domains"] for domain in domains) and
                len(domains) == len(set(domains)), "invalid_profile", "Provider domains must be distinct approved egress domains")
        consumers["provider:" + provider["id"]] = "model"
        expected_providers.add((provider["credential_ref"], "provider:" + provider["id"]))
    seen, purposes, refs = set(), {}, set()
    for binding in sequence(profile["credential_bindings"], "credential bindings"):
        fields(binding, ("ref", "consumer", "purpose", "max_bytes"), "credential binding")
        identifier(binding["ref"])
        require(isinstance(binding["consumer"], str) and binding["consumer"] in consumers and
                binding["ref"] in profile["credential_refs"] and binding["purpose"] == consumers[binding["consumer"]],
                "invalid_profile", "Credential requires an approved consumer and development/model purpose")
        positive(binding["max_bytes"], "credential size limit")
        require(binding["max_bytes"] <= 65536, "invalid_profile", "Credential size limit exceeds 64 KiB")
        pair = (binding["ref"], binding["consumer"])
        require(pair not in seen and purposes.get(binding["ref"], binding["purpose"]) == binding["purpose"],
                "invalid_profile", "Duplicate credential binding or mixed credential purposes")
        if binding["consumer"].startswith("provider:"):
            require(pair in expected_providers, "invalid_profile", "Provider may receive only its declared credential reference")
        seen.add(pair)
        refs.add(binding["ref"])
        purposes[binding["ref"]] = binding["purpose"]
    require(refs == set(profile["credential_refs"]) and expected_providers <= seen,
            "invalid_profile", "Unused credential references or missing provider bindings")
    require(sum(binding["max_bytes"] for binding in profile["credential_bindings"]) <= profile["resources"]["disk_mb"] * 1048576,
            "invalid_profile", "Credential staging exceeds the approved preparation budget")


def credential_target(ref, consumer):
    identifier(ref)
    require(isinstance(consumer, str) and re.fullmatch(r"(?:service|provider):[A-Za-z0-9][A-Za-z0-9_-]{0,63}", consumer),
            "invalid_profile", "Expected service/provider credential consumer")
    kind, name = consumer.split(":")
    return f"/run/credentials/{kind}/{name}/{ref}"


def environment_policy(profile, artifact_id):
    validate_profile(profile)
    require(profile["version"] == 3, "runtime_missing", "Environment planning requires profile v3")
    hash_value(artifact_id)
    egress = bool(profile["network"]["allowed_domains"])
    services = ["service:" + service["id"] for service in profile["services"]]
    components = (["proxy"] if egress else []) + services
    members = ["worker"] + components
    networks = [{"id": "internal", "name": "routine-" + artifact_id[:24] + "-internal", "internal": True,
                 "ipv6": False, "members": members}]
    if egress:
        networks.append({"id": "egress", "name": "routine-" + artifact_id[:24] + "-egress", "internal": False,
                         "ipv6": False, "members": ["proxy"]})
    flows = []
    if egress:
        flows.append({"source": "worker", "destination": "proxy", "protocol": "tcp", "port": 3128})
        flows.append({"source": "proxy", "destination": "public-ipv4", "protocol": "tcp", "port": 443})
        for server in profile["network"]["dns_servers"]:
            flows.extend({"source": "proxy", "destination": server, "protocol": protocol, "port": 53} for protocol in ("udp", "tcp"))
    for service in profile["services"]:
        flows.extend({"source": "worker", "destination": "service:" + service["id"], "protocol": "tcp", "port": port}
                     for port in service["ports"])
    credentials = [{**binding, "target": credential_target(binding["ref"], binding["consumer"]), "delivery": "read-only-file"}
                   for binding in profile["credential_bindings"]]
    gates = ["host_setup_approval", "firewall_backend", "dns_no_bypass", "disk_enforcement", "real_network_qualification"]
    if egress:
        gates.append("encrypted_routing")
    if services:
        gates.append("service_readiness")
    if credentials:
        gates.append("credential_broker")
    if profile["providers"]:
        gates.append("provider_configuration")
    return {"version": 1, "artifact_id": artifact_id, "activation_enabled": False,
            "runtime": profile["runtime"], "resources": profile["resources"], "components": components,
            "services": profile["services"], "providers": profile["providers"], "credentials": credentials,
            "constraints": {"pull_policy": "never", "privileged": False, "capabilities": [], "no_new_privileges": True,
                            "published_ports": [], "restart": "no", "proxy_read_only_root": True, "services_read_only_root": True,
                            "service_storage": "only-declared-bounded-tmpfs", "docker_socket": False, "ssh_agent": False,
                            "inherit_host_credentials": False, "worker_tool_location": "container-local-opencode",
                            "host_mounts": "approved-snapshots-and-consumer-credential-files-only"},
            "networks": networks, "proxy_policy": {"allowed_domains": profile["network"]["allowed_domains"], **profile["network"]["proxy"]} if egress else None,
            "firewall": {"default": "deny", "flows": flows, "ipv6": "deny", "host_lan": "deny", "cross_environment": "deny",
                         "replies": "only-established-authorized-flows", "dns": {"worker": "local-service-names-only-no-forwarding",
                         "services": "disabled", "proxy": "approved-public-resolvers-only"},
                         "enforcement_points": ["host-input", "host-forward-before-docker-accept", "same-bridge", "container-dns"],
                         "address_exclusions": "verified-host-addresses-connected-routes-and-special-use",
                         "endpoint_binding": "verified-container-interface-identities-no-subnet-only-trust"},
            "open_gates": gates}


def allows_flow(plan, source, destination, protocol, port):
    """Pure policy oracle for tests/review. Not a firewall or encrypted-route gate."""
    if type(port) is not int or protocol not in ("tcp", "udp"):
        return False
    for flow in plan["firewall"]["flows"]:
        if flow["source"] == source and flow["protocol"] == protocol and flow["port"] == port:
            if flow["destination"] == "public-ipv4":
                if public_ipv4(destination):
                    return True
            elif flow["destination"] == destination:
                return True
    return False
