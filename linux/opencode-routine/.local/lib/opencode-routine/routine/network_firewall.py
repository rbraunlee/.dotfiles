"""Concrete nftables JSON batches for a candidate trusted administration helper.

No rules are executed here. Independent normalized readback is mandatory. Hook
placement/bridge visibility and actual approved connectivity remain unqualified.
"""
import ipaddress
import re

from .contracts import require
from .policy import EXCLUDED_V4


def interface(value):
    require(isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,15}", value),
            "invalid_runtime", "Invalid trusted interface name")
    return value


def match(left, right, op="=="):
    return {"match": {"op": op, "left": left, "right": right}}


def meta(key):
    return {"meta": {"key": key}}


def payload(protocol, field):
    return {"payload": {"protocol": protocol, "field": field}}


def ct(key):
    return {"ct": {"key": key}}


def rule(family, table, chain, expressions):
    return {"add": {"rule": {"family": family, "table": table, "chain": chain, "expr": expressions}}}


def chain(family, table, name, hook, priority, policy="accept"):
    return {"add": {"chain": {"family": family, "table": table, "name": name,
                             "type": "filter", "hook": hook, "prio": priority, "policy": policy}}}


def exclusions(inventory):
    values = {str(network) for network in EXCLUDED_V4}
    for value in inventory["host_addresses"]:
        address = ipaddress.IPv4Address(value)
        values.add(str(ipaddress.IPv4Network(str(address) + "/32")))
    for value in inventory["connected_routes"]:
        network = ipaddress.IPv4Network(value, strict=True)
        require(network.prefixlen > 0, "invalid_runtime", "A default route is not a connected-route observation")
        values.add(str(network))
    return sorted(values)


def firewall_batch(plan, inventory, networks, bindings):
    """Create a private table snapshot; helper atomically replaces only this owner.

    No generic established/related accept. Each permitted reverse direction is
    paired with an exact endpoint/port and established conntrack state. Unknown
    endpoints receive only the scoped final drop; subnet membership grants nothing.
    """
    table = "routine_" + plan["artifact_id"][:24]
    bridges = [interface(value["bridge"]) for value in networks.values()]
    commands = []
    denied = exclusions(inventory)
    for family in ("inet", "bridge"):
        commands.append({"add": {"table": {"family": family, "name": table}}})
        commands.append(chain(family, table, "forward", "forward", -150))
    commands.append(chain("inet", table, "input", "input", -150))
    commands.append(chain("inet", table, "output", "output", -150))
    commands.append(chain("bridge", table, "input", "input", -150))
    commands.append(chain("bridge", table, "output", "output", -150))
    for bridge in bridges:
        commands.append(rule("inet", table, "input", [match(meta("iifname"), bridge), {"drop": None}]))
        commands.append(rule("inet", table, "output", [match(meta("oifname"), bridge), {"drop": None}]))
        for direction in ("iifname", "oifname"):
            commands.append(rule("inet", table, "forward", [match(meta(direction), bridge),
                            match(meta("nfproto"), "ipv6"), {"drop": None}]))

    # Endpoint admission is grounded in trusted host-veth/MAC readback. Every
    # packet on a routine bridge must originate from an admitted veth and address.
    for component, endpoints in bindings.items():
        for endpoint in endpoints:
            bridge = networks[endpoint["logical_id"]]["bridge"]
            veth = interface(endpoint["host_veth"])
            # inet ingress sees the bridge, bridge hooks see the actual veth.
            commands.append(rule("bridge", table, "forward", [match(meta("iifname"), veth),
                match(payload("ether", "saddr"), endpoint["mac"], "!="), {"drop": None}]))
            commands.append(rule("bridge", table, "forward", [match(meta("iifname"), veth),
                match(payload("ether", "type"), "ip"),
                match(payload("ip", "saddr"), endpoint["ipv4_address"], "!="), {"drop": None}]))
            commands.append(rule("bridge", table, "input", [match(meta("iifname"), veth),
                match(meta("iif"), endpoint["host_ifindex"]), match(payload("ether", "saddr"), endpoint["mac"]),
                match(payload("ether", "type"), "ip"), match(payload("ip", "saddr"), endpoint["ipv4_address"]), {"accept": None}]))
            commands.append(rule("bridge", table, "output", [match(meta("oifname"), veth),
                match(meta("oif"), endpoint["host_ifindex"]), match(payload("ether", "type"), "ip"),
                match(payload("ip", "daddr"), endpoint["ipv4_address"]), {"accept": None}]))

    def endpoint(component, logical_id):
        return next((entry for entry in bindings.get(component, []) if entry["logical_id"] == logical_id), None)

    for index, flow in enumerate(plan["firewall"]["flows"], 1):
        external = flow["destination"] == "public-ipv4" or flow["destination"] in inventory["dns_servers"]
        logical = "egress" if external else "internal"
        source = endpoint(flow["source"], logical)
        destination = None if external else endpoint(flow["destination"], logical)
        if not source or (not external and not destination):
            continue
        bridge = networks[logical]["bridge"]
        dst = flow["destination"] if external else destination["ipv4_address"]
        proto, port = flow["protocol"], flow["port"]
        # Public destination exclusions precede port admission, even when the
        # host has a public address or a connected globally routed LAN prefix.
        if external:
            for block in denied:
                commands.append(rule("inet", table, "forward", [match(meta("iifname"), bridge),
                    match(payload("ip", "saddr"), source["ipv4_address"]),
                    match(payload("ip", "daddr"), {"prefix": {"addr": block.split("/")[0], "len": int(block.split("/")[1])}}),
                    {"drop": None}]))
        mark = (int(plan["artifact_id"][:6], 16) << 8) | index
        require(index < 256, "input_limit", "Firewall flow-mark allocation exceeds its bound")
        for reverse in (False, True):
            expressions = [match(meta("nfproto"), "ipv4"), match(meta("l4proto"), proto),
                           match(meta("oifname" if reverse else "iifname"), bridge),
                           match(meta("oif" if reverse else "iif"), networks[logical]["bridge_ifindex"]),
                           match(payload("ip", "daddr" if reverse else "saddr"), source["ipv4_address"])]
            if dst != "public-ipv4":
                expressions.append(match(payload("ip", "saddr" if reverse else "daddr"), dst))
            expressions.append(match(payload(proto, "sport" if reverse else "dport"), port))
            if reverse:
                expressions.append(match(ct("state"), "established"))
            expressions.append(match(ct("mark"), mark) if reverse else {"mangle": {"key": ct("mark"), "value": mark}})
            commands.append(rule("inet", table, "forward", expressions + [{"accept": None}]))
            if not external:
                sender, receiver = (destination, source) if reverse else (source, destination)
                bridge_expr = [match(meta("iifname"), sender["host_veth"]),
                               match(meta("oifname"), receiver["host_veth"]),
                               match(meta("iif"), sender["host_ifindex"]), match(meta("oif"), receiver["host_ifindex"]),
                               match(payload("ether", "saddr"), sender["mac"]),
                               match(payload("ip", "saddr"), sender["ipv4_address"]),
                               match(payload("ip", "daddr"), receiver["ipv4_address"]),
                               match(meta("l4proto"), proto), match(payload(proto, "sport" if reverse else "dport"), port)]
                if reverse:
                    bridge_expr.append(match(ct("state"), "established"))
                commands.append(rule("bridge", table, "forward", bridge_expr + [{"accept": None}]))

    # ARP is allowed only for verified sender identities; unknown peers/IPv6/non-IP
    # do not get an implicit same-bridge exception. Host-bound ARP/routing still
    # needs live qualification; this checkpoint does not claim connectivity.
    for endpoints in bindings.values():
        for entry in endpoints:
            for hook in ("input", "forward"):
                commands.append(rule("bridge", table, hook, [match(meta("iifname"), entry["host_veth"]),
                    match(meta("iif"), entry["host_ifindex"]), match(payload("ether", "saddr"), entry["mac"]),
                    match(payload("ether", "type"), "arp"),
                    match(payload("arp", "saddr ip"), entry["ipv4_address"]), {"accept": None}]))
            commands.append(rule("bridge", table, "output", [match(meta("oifname"), entry["host_veth"]),
                match(meta("oif"), entry["host_ifindex"]), match(payload("ether", "type"), "arp"),
                match(payload("arp", "daddr ip"), entry["ipv4_address"]), {"accept": None}]))
    for bridge in bridges:
        for direction in ("iifname", "oifname"):
            commands.append(rule("inet", table, "forward", [match(meta(direction), bridge), {"drop": None}]))
        # ibrname/obrname catch unknown/unadmitted veths on the owned bridge.
        for direction in ("ibrname", "obrname"):
            commands.append(rule("bridge", table, "forward", [match(meta(direction), bridge), {"drop": None}]))
        commands.append(rule("bridge", table, "input", [match(meta("ibrname"), bridge), {"drop": None}]))
        commands.append(rule("bridge", table, "output", [match(meta("obrname"), bridge), {"drop": None}]))
    return {"owner": plan["artifact_id"], "table": table, "replacement": "atomic-owned-tables-only",
            "nftables": commands}


def dns_batch(plan, component, container_id, identity, attachments):
    """Filter OUTPUT before Docker embedded-resolver DNAT, not just host port 53."""
    table = "routine_dns"
    commands = [{"add": {"table": {"family": "inet", "name": table}}},
                chain("inet", table, "output", "output", -300)]
    commands.append(rule("inet", table, "output", [match(meta("nfproto"), "ipv6"), {"drop": None}]))
    commands.append(rule("inet", table, "output", [match(payload("ip", "daddr"), "127.0.0.11"), {"drop": None}]))
    servers = sorted({flow["destination"] for flow in plan["firewall"]["flows"]
                      if flow["source"] == "proxy" and flow["port"] == 53}) if component == "proxy" else []
    for proto in ("udp", "tcp"):
        for server in servers:
            commands.append(rule("inet", table, "output", [match(meta("l4proto"), proto),
                match(payload("ip", "daddr"), server), match(payload(proto, "dport"), 53), {"accept": None}]))
        commands.append(rule("inet", table, "output", [match(meta("l4proto"), proto),
                        match(payload(proto, "dport"), 53), {"drop": None}]))
    hosts = {name.split(":", 1)[-1]: entries[0]["ipv4_address"] for name, entries in attachments.items()
             if name.startswith("service:") or name == "proxy"} if component == "worker" else {}
    resolv = "".join("nameserver " + server + "\n" for server in servers) if servers else "nameserver 127.0.0.1\noptions attempts:1 timeout:1\n"
    return {"owner": plan["artifact_id"], "component": component, "container_id": container_id,
            "identity": identity, "nftables": commands, "hosts": hosts, "resolv_conf": resolv,
            "read_only_files": True, "pre_docker_dns_dnat": True,
            "consumer_start_interlocked": True, "survives_consumer_start": True}
