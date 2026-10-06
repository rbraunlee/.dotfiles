> **Historical copy (2026-10-06)** of root `docs/m2-services-proposal.md`. Deferred sandbox services proposal, not qualified delivery.
> Original root note remains ignored and untouched. Paths written as `docs/...` below refer to original drafting locations; use [the package history index](../README.md) for relocated files.

# M2 C1 services / scoped source / provider preparation

**Status:** offline implementation checkpoint only. Production `Environment`
still uses `DisabledEnvironmentAdapter`. No runtime enable flag, profile extension,
worker asset change, credential provisioning, Docker launch or host administration
is part of this checkpoint. M2/Gate A remain unaccepted.

## Owned implementation and interfaces

- `routine/service_adapters.py`: explicit-injection `ServiceEnvironmentAdapter`.
  Implements existing `preflight`, `create_networks`, `enforce_policy`,
  `start_component`, `wait_ready`, `stop_components` lifecycle. Networking and proxy
  lifecycle are delegated; there is no networking implementation in this module.
- `routine/credential_sources.py`: opt-in `ScopedFileCredentialBroker`, observable
  `resolve(request, binding, timeout=None) -> bytearray` interface. Existing
  `credentials.py` is **unchanged and was not inspected after read permission was
   denied**. Coordinator integration now tests its observable `path`/`stage`/
   `cleanup` interface with fake secrets; code inspection and live delivery remain
   unqualified.
- `routine/provider_config.py`: pure `provider_preparation(plan)` returns a
  **routine-owned, non-executable preparation manifest**. It is not OpenCode
  configuration and does not claim provider support or connectivity.

Constructor boundary:

```python
ServiceEnvironmentAdapter(
    artifact_root, network,
    checkpoint=checkpoint,       # required trusted durable journal callback
    credential_path=resolver,    # optional trusted delivery bridge, not caller paths
    docker=injected_transport,
    monotonic=clock,
)
checkpoint(plan, component, event, metadata)
resolver(plan, approved_binding) -> absolute_path
```

Checkpoint events are `create-intent` (nonce, image, plan hash), `created` (nonce,
immutable container ID), `start-intent`, `stop-intent`, and `stopped` (ID). They
contain no delivery paths, values, actual secret sizes, secret hashes or diagnostics.
The Coordinator now wires `bind_host_interfaces` to `EnvironmentCheckpoint` and
the existing delivery primitive's scoped path lookup before preflight. Networking
uses the same durable sink; service events are prefixed `service-`. The Coordinator
owns recovery authority. An in-memory
adapter is not restart recovery. A stopping-checkpoint failure does not skip the
stop attempt, but prevents a confirmed lifecycle result.

The frozen NetworkAdapter attachment result is a list of dictionaries with exactly
`logical_id`, `network_id`, `name`, `ipv4_address`. Services require one approved
internal network. No caller-supplied aliases, DNS options or Compose fragments are
accepted. A fixed DNS-safe service identity is derived by `service_identity()` from
the approved component; this is also its Compose service key, avoiding an accidental
shared `service` DNS alias across components. Compose's owned container-name alias
is allowed. Service DNS is loopback-only with no search domain expansion.

`verify_component(plan, component, inspection, timeout)` must prove pre-start
bootstrap, exact endpoint ownership and installed DNS/packet enforcement. It must
raise on refusal; normal success may return `None` or literal `True`. Other results
are rejected. Proxy `stop_proxy` must return **literal `True`**, not merely truthy.

## Bounded service lifecycle

1. Preflight the injected networking gate, daemon resource/quota support and pinned
   local service images. Reject image-declared anonymous volumes.
2. Obtain approved owned attachment metadata after policy enforcement. Require an
   exact, complete set of this service's approved delivery bindings. Provider keys
   are never resolved or supplied. Proxies receive no credentials.
3. Refuse pre-existing containers; journal intent/nonce before side effects. Retain
   private generated Compose files. Create stopped with `--no-recreate`, no build
   and no pull; pin and checkpoint the immutable container ID.
4. Inspect effective image/user, read-only root, capabilities, namespaces, mounts,
   network identity, CPU/memory/no-swap/PID/disk/log/tmpfs bounds and DNS settings.
   Ask networking for its pre-start enforcement proof. Reinspect before starting
   the immutable ID. A failed proof/configuration cannot start the application.
5. Execute approved readiness argv through Docker **inside that container**. Discard
    bounded raw output. Reject late success and effective-configuration drift;
    reverify effective network/namespace/DNS identity after readiness.
6. Stop requested components in the supplied reverse order using verified immutable
   IDs and one shared stop deadline; continue other stops after a component failure
   while budget remains. Ambiguous creation can be reconciled for stopping only
   with this preparation's nonce; it is never reusable dispatch authority.

No `down`, `rm`, pruning, volume/network deletion, limit removal or adoption of a
foreign/pre-existing resource is implemented. Delivery cleanup remains the existing
controller's responsibility, **only** after a confirmed-stop result.

Readiness timeout kills/bounds the host Docker client, not independently the
container-local exec process. The controller must stop and confirm the container;
uncertain stopping retains files and holds dispatch. Fine-grained in-container
cancellation is not claimed by this component.

## Scoped trusted source

Trusted administration supplies a private absolute root and an immutable snapshot
of exact grants:

```python
{
    "authorization_id": approved_authorization_hash,
    "binding": {"ref": approved_ref, "consumer": approved_consumer,
                "purpose": "development", "max_bytes": approved_bound},
    "source": "private-relative-file",
}
```

Model grants require purpose `model` and a provider consumer. Authorization and the
complete consumer binding must match before source descriptors are opened. No
environment inheritance, home/auth-store discovery, command execution, inline
secret values or Coordinator-controlled source paths are supported.

The source root is inode-pinned without reading a secret. Descriptor-relative
no-follow walking rejects unsafe ancestry, nonprivate directories, cross-device
source entries, symlinks, nonregular/multiply-linked files and source replacement.
Source files require current-user ownership and mode `0600`; source directories
require `0700`. Reads are limited to the approved maximum and checked before/after
against identity/size/metadata and deadlines. Mutable read buffers are wiped on
failure, scratch buffers on every path; successful results are erasable bytearrays
for the delivery consumer to wipe. Errors contain generic codes/messages only.

**Limits:** local regular-file deadline checks do not qualify killable reads on an
arbitrary remote filesystem, same-device bind-mount exclusion or locked-memory
erasure. Source grants/provisioning/rotation and their trusted administrator are not
installed by this module. No real credential source was read in testing.

## Explicit blockers and next approvals

1. **Delivery bridge:** obtain permission to inspect the unchanged delivery primitive
    and qualify its private path/inode handoff. Combined offline tests now use the
    existing primitive with fake secrets and scoped path lookup. Path metadata/read-only Docker inspection does not
   qualify a descriptor-pinned bind handoff or demonstrate actual consumer access,
   cross-consumer denial, real cleanup or UID readability.
2. **Durable ownership integration:** implemented and tested in the host ledger;
    real administration transport and crash/restart qualification remain open.
    Production is not enabled; general crash/resume remains M5.
3. **Real pre-start network proof:** approve a specific host enforcement/bootstrap
   design and then disposable qualification. The adapter intentionally refuses
   missing effective network IDs/IPs; Docker may expose these only after endpoint
   activation. Any trusted pre-start bootstrap/namespace helper must establish the
   proof without running an application first. Static IP requests or Docker DNS
   options alone are not proof of isolation/no forwarding.
4. **Service/source qualification:** separately approve exact pinned local images,
   topology, resources, fake-source root and disposable fake-secret tests before
   any live launch/mount/network operation. Only subsequently approved trusted
   source provisioning may introduce real development/model credentials.
5. **Provider mapping:** supply authoritative **local pinned OpenCode V2.0.22
   source/docs**. Approve a trusted mapping of provider ID, SDK/protocol, exact
   endpoints/models and supported credential-file consumption, plus configuration
   discovery/plugin/MCP isolation. Current profile fields cannot establish these.
   `executable_opencode_configuration()` unconditionally refuses, including callers
   supplying `qualified=True`. No shared schema or OpenCode field was guessed.
6. Provider endpoint/egress and encrypted-routing qualification, existing storage
   gates and remaining M2 acceptance still require their separate approvals/evidence.

## Validation boundary

Tests use injected Docker/network transports, a fake clock and temporary fake
credential files only. They establish call ordering, scoped source/delivery
metadata, refusal paths, retained ownership, deadline handling and non-executable
provider preparation—not Docker isolation, actual packet enforcement or OpenCode
provider configuration. The existing production-disabled tests remain in place.

Final offline checkpoint: **46 new tests pass** (26 service adapter, 13 scoped
source, 7 provider preparation). Complete normal suite: **256 total, 238 passed,
18 live tests skipped**, Python 3.14. No live opt-in was enabled:

```sh
env -u OPENCODE_ROUTINE_TEST_IMAGE \
    -u OPENCODE_ROUTINE_COMPONENT_IMAGE \
    -u OPENCODE_ROUTINE_STORAGE_IMAGE \
    python3 -B -m unittest discover -s linux/opencode-routine/tests
```

The isolated services copy has no Git metadata; no commit was created. Its files
are ready for Coordinator review/integration, not production activation.
