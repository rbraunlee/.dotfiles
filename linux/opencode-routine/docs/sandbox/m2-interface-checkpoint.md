> **Historical copy (2026-10-06)** of root `docs/m2-interface-checkpoint.md`. Deferred sandbox offline interface checkpoint, not real qualification.
> Original root note remains ignored and untouched. Paths written as `docs/...` below refer to original drafting locations; use [the package history index](../README.md) for relocated files.

# M2 parallel interface checkpoint — 2026-10-04

Implementation authorization supersedes the storage-first pause, not live setup
or qualification gates. Copies were seeded from current untracked/ignored files.
M3 and later milestones remain out of scope. Production activation stays disabled.

## Ownership and checkpoints

- **S1 storage:** retention modules/tests and `m2-storage-proposal.md`; bounded
  one-shot retained inspection components and privileged handoff/restart proposals.
  General interruption/resume is M5, not S1.
- **N1 networking:** networking/network modules/tests and `m2-network-proposal.md`;
  concrete injectable network/firewall/DNS/proxy adapters and offline failure tests.
- **C1 services/credentials:** service adapters, new credential source, provider
  preparation/tests and `m2-services-proposal.md`. Existing `credentials.py` is not
  changed because access was denied. Executable OpenCode provider configuration
  remains blocked pending an authoritative mapping and sufficient profile inputs.
- **Integration:** shared environment/policy/contracts, README, plan and
  qualification documents belong to the coordinating agent.

## Network/service contract

`NetworkAdapter` supplies `preflight(plan, timeout)`,
`create_networks(plan, timeout)`, `enforce_policy(plan, timeout)`,
`component_networks(plan, component)`,
`verify_component(plan, component, container_inspect, timeout)`, and proxy
`start_proxy`, `wait_proxy_ready`, `stop_proxy` with `(plan, timeout)` arguments.

Attachment metadata is a list of dictionaries containing `logical_id`,
`network_id`, `name` and `ipv4_address`. No arbitrary Compose fragments, aliases or
DNS overrides are accepted from consumers. Unknown/unowned attachments fail.

`ServiceEnvironmentAdapter` preserves the existing environment lifecycle API and
delegates network/proxy operations. Consumers are created stopped, inspected and
verified before start by immutable ID. Verification must establish effective
endpoint and DNS enforcement, not just requested configuration. Docker embedded
DNS forwarding requires an approved trusted bootstrap/readback mechanism; neither
`--dns` nor bridge separation constitutes proof.

Services' fixed generated Compose identity/container/ID aliases are validated
internally by both adapters; arbitrary attachment aliases remain prohibited.
Lifecycle failures raise sanitized errors. Stop operations return strict `True`
only after confirmed stopping. Intent and ownership checkpoint callbacks are
injectable. Coordinator-owned `EnvironmentCheckpoint` now wires both adapters to
the existing host ledger, and `InspectionLedger` supplies dedicated inspection
records and cooperative source locking. Neither enables production execution.
Networks, protective rules, stopped containers and evidence are retained.

## Storage and credential boundaries

Inspection requests identify project/feature/run only, never paths or commands.
The source is freshly admitted, exclusively leased and descriptor-pinned. Trusted
xattr visibility and stable mount identity are required. Descriptor-based staging
outside Docker's data root is a proposal, not a qualified mount transport;
`/proc/self/fd` is not a Docker daemon handoff mechanism. Production inspection
remains unconditionally denied.

Credential source interface remains `resolve(request, binding, timeout=None)`
returning an erasable byte buffer. Grants pin authorization and consumer binding;
service checks resolve only development service bindings. Proxies receive none;
provider keys are not resolved by service checks. Provider preparation is
secret-free and does not authorize worker activation or provider calls.

## Separate approvals still required

Privileged source inspection/mount handoff, Docker restart, firewall/namespace
setup, external endpoint qualification and real development/model credential use
each require explicit bounded approval. Offline injected-adapter passes do not
establish live isolation or M2 acceptance. Limits, ledgers and retained evidence
must not be weakened, reset or deleted.
