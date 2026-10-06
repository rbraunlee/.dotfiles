> **Historical copy (2026-10-06)** of root `docs/m2-network-proposal.md`. Deferred sandbox network proposal, not installed enforcement.
> Original root note remains ignored and untouched. Paths written as `docs/...` below refer to original drafting locations; use [the package history index](../README.md) for relocated files.

# N1 proposal — owned nftables guard and interlocked DNS bootstrap

**Status:** injectable offline implementation only; no host setup approved here.
**Bound:** M2 network/firewall/DNS/proxy adapters. No worker/image changes, real
credentials, external access, namespace operations, installed rules or live Docker
requests. Neither N1 tests nor a proxy health result establish M2 acceptance.

## Implemented interfaces and ownership

`routine/networking.py` exports `NetworkAdapter`:

```python
NetworkAdapter(docker=None, admin=None, checkpoint=None, artifact_root=None,
               clock=time.monotonic, sleep=time.sleep)
preflight(plan, timeout)
create_networks(plan, timeout)
enforce_policy(plan, timeout)
component_networks(plan, component)
verify_component(plan, component, container_inspect, timeout)
start_proxy(plan, timeout)
wait_proxy_ready(plan, timeout)
stop_proxy(plan, timeout)
```

`component_networks` returns only a list of dictionaries with `logical_id`,
`network_id`, `name`, and `ipv4_address`. It is unavailable until initial deny
rules have exact independent readback. Network/proxy create operations are
nonretryable after an attempt; existing names cannot be adopted. Stop addresses
only the locally pinned, verified immutable proxy ID and returns strict `True`
only after confirmed not-running/not-paused/not-restarting state.

Networking owns these new modules, their new tests and this proposal. Coordinator
owns shared policy/contracts/lifecycle integration and durable journaling. Services
owns service creation, configuration, credential delivery and readiness. Services
must create an owned consumer before calling `verify_component`, and must not run
its workload until verification succeeds. Required inspection labels are
`routine.artifact-id`, `routine.component`, and a private 32-hex
`routine.launch-id`; service creation provenance is services' responsibility.

## Concrete injection protocols

`DockerNetworkTransport(request)` calls
`request(method, api_path, json_body_or_none, timeout)` and requires decoded Docker
API JSON. It constructs network list/create/inspect, local image inspect, container
list/create/inspect/start/stop requests. No shell commands, pull, replace, remove,
Compose `down`, or prune exists. The trusted caller must pin a local socket/daemon,
validate HTTP statuses, bound responses, and enforce cancellation. The adapter also
bounds decoded responses to 1 MiB and rejects late results.

`NetworkAdminTransport(exchange)` calls `exchange(operation, payload, timeout)`:

- `host_inventory`: verified daemon/boot/observation identity, host addresses,
  connected routes, capabilities, hook priorities, and bounded private IPAM/bridge
  reservations. Reservations must not overlap each other or observed routes.
- `observe_network`: independently observed network ID, bridge name and numeric
  ifindex bound to the host boot identity.
- `read_host_identity`: exact unchanged daemon/boot/observation/address/route/hook
  subset. Drift holds admission rather than silently broadening exclusions.
- `apply_firewall` / `read_firewall`: atomic replacement of only this owner's
  private `inet` and `bridge` tables; independently normalized effective snapshot
  must equal the requested batch, not merely return its hash or an acknowledgment.
- `prepare_held_component` / `observe_component`: trusted pinned namespace
  device/inode/boot identity and actual host-veth/MAC/IP/network/ifindex binding.
  First admission requires the workload held; later observation must preserve the
  same namespace/interfaces. Both require a consumer-start interlock that survives
  Docker start.
- `apply_component_dns` / `read_component_dns`: namespace nftables rules and
  read-only hosts/resolver files, with exact identity-bound effective readback.

Namespace proof endpoint fields: `logical_id`, `network_id`, `ipv4_address`,
`bridge_ifindex`, `host_ifindex`, `container_ifindex`, `host_veth`, `mac`.
Unrecognized diagnostic fields are not exported into checkpoints.

There is **no concrete privileged helper or default executor**. Missing Docker,
trusted bootstrap, or checkpoint injection refuses preflight. There is no profile
or Coordinator enable flag. Explicit injection is a test/administration seam, not
an approval/qualification authority.

## Enforcement candidate and ordering

1. Synchronously checkpoint creation intent and private preparation nonce.
2. Create isolated networks with exact IPAM/labels; pin returned immutable IDs;
   inspect exact effective topology and observe bridge ifindexes.
3. Install initial default-deny scoped rules **before any consumer starts**.
4. Obtain held namespace/interface identity; reject unknown peers, extra
    attachments, unapproved aliases/links, published ports, host networking and
    IPv6. Services permit only their fixed generated Compose identity/container/ID
    aliases; worker/proxy consumers permit none.
5. Install/read namespace DNS rules/files; update/read endpoint-bound host rules.
6. Only then allow service/proxy workload startup. Proxy health verifies actual
   policy/bundle bytes, read-only policy, non-root UID and invalid-request denial.
   Readiness rechecks namespace and host identity, not only Docker health status.

Generated batches use nftables JSON `add table/chain/rule` expressions, not the
pure policy oracle. Host filter hook priority is `-150`: after the observed
conntrack priority `-200`, before observed Docker acceptance `0`. Both routed and
same-bridge paths are covered. Host input and locally generated output to routine
bridges are denied. Allowed pairs match exact addresses/ports and trusted numeric
interface IDs; bridge rules also match MAC/veth identities. Replies require exact
flow pairing and established conntrack state/owner-derived flow marks, not a broad
established/related exception. Public egress excludes special-use addresses,
observed host addresses (including public ones) and connected routes.

The helper must reserve marks/table names exclusively and reconcile atomic snapshots
without touching unrelated tables. Mark/table collision admission and concurrent
host-admin ownership remain helper qualification requirements; truncated owner
identifiers are not alone an exclusive allocation proof.

### Docker embedded DNS bypass

Docker's `127.0.0.11` forwarding cannot be denied merely by internal bridges,
`--dns`, or host-forward port-53 rules. Namespace OUTPUT filtering is generated at
`-300`, **before** observed Docker DNS DNAT `-100`: deny all destinations at
`127.0.0.11` regardless of rewritten port, deny IPv6, allow proxy UDP/TCP port 53
only to explicit approved resolvers, deny all other consumer DNS.

Workers receive only generated static local service/proxy hosts mappings. Services
receive no name-forwarding capability. Proxy resolver files list only approved
numeric resolvers. Exact rules/files/namespace readback is required. This design
does not pretend Docker `--dns` overrides embedded DNS.

## Checkpoint and retention contract

`checkpoint(event_dict)` must synchronously durably journal before returning.
Coordinator integration now supplies `EnvironmentCheckpoint` from
`routine/checkpoints.py`, shared by service and network adapters. Combined offline
tests exercise actual ledger writes; this does not qualify a privileged transport.
Events include plan hash, artifact/preparation IDs; creation intent precedes side
effects, and immutable IDs precede workload start. Firewall/DNS intent retains
exact transaction construction; verified events retain allowlisted identities and
hashes. Coordinator must prevent raw helper/transport diagnostics from being
exported. Checkpoints contain no credential values, hashes or provider secrets.

A failed/ambiguous admission holds subsequent consumer admission. Callback failure
after proxy identity capture retains the local ID for a verified explicit stop.
Lost/unknown creation IDs are never guessed from a name. Restart adoption is not
implemented: durable identities need explicit future administrative reconciliation.

Stopping retains protective rules, networks, stopped containers, policy files and
evidence. No removal hooks or rollback that weakens protection exists in N1.

## Evidence and next approval

Offline tests exercise concrete Docker API bodies, nftables expressions, independent
effective readbacks, DNS transactions, identity/collision/drift rejection,
pre-consumer ordering, deadlines, checkpoint failures, immutable-ID lifecycle and
retention. They **do not execute or syntax-qualify nftables**, create namespaces,
exercise packets, or prove encrypted HTTP routing.

**Next bounded approval: N1-Q — disposable network/bootstrap qualification.**
Before any host mutation, propose and obtain approval for the exact helper binary,
local transport permissions, interface/address reservations, exclusive table/mark
allocation, hook/conntrack prerequisites and retained fixture limits. A stopped
Docker container is not itself proof that its final namespace exists: the helper
must provide a qualified namespace/start interlock without executing consumer code
early or replacing the namespace/rules during start. The current image is unchanged;
no assumed bootstrap mechanism has been smuggled into its entrypoint.

Then qualify nftables parsing/installation/readback; initial-deny race windows;
same-bridge and routed approved flows; spoofed IP/MAC/veth identity; host/LAN/public
host/cross-slice/IPv6/direct-egress denials; embedded-resolver UDP/TCP forwarding,
arbitrary rewritten ports and alternate resolvers; namespace/route drift and
daemon/restart/interruption; listener readiness and confirmed stop/retention.
Continuous identity/route monitoring or a fail-closed lease must hold workloads on
post-admission drift, not just recheck at startup/readiness.

Real approved endpoint access, transparent CONNECT/shared-endpoint encrypted-routing
risk, services/providers/credentials and complete M2 acceptance remain separate
gates. No external access or real secrets are needed or authorized by N1.
