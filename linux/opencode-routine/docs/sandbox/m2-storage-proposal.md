> **Historical copy (2026-10-06)** of root `docs/m2-storage-proposal.md`. Deferred sandbox storage proposal; host procedures require separate approval.
> Original root note remains ignored and untouched. Paths written as `docs/...` below refer to original drafting locations; use [the package history index](../README.md) for relocated files.

# M2 / S1 — one-shot retained-checkout inspection

**Status:** offline components implemented; production inspection remains
unconditionally disabled. This proposal is not permission to install/run a root
helper, create mounts, restart Docker, change configuration or enable an API.
No M5 crash/resume, merged-layer reconstruction, cleanup or quota weakening.

## Ownership and checkpoint

Storage owns `routine/retention.py`, `routine/retention_helper.py`,
`routine/retention_lifecycle.py`, `tests/test_m2_retention*.py` and this document.
The Coordinator owns shared state/integration, environment/policy/contracts,
README and plan/qualification updates. Worker assets and image identities remain
unchanged. Existing stopped baseline outcomes never become inspection success or
integration authority.

**S1:** identifiers → trusted run read → source lease/admission → privileged
descriptor scan → pinned handoff → bounded trusted inspector → confirmed stop →
source recheck → owned handoff release → separate inspection result.

There is no installed CLI/service, sudo rule, mount syscall implementation, Docker
inspection adapter or production activation. Coordinator integration now supplies
`InspectionLedger` in `routine/checkpoints.py`: dedicated atomic ledger records,
identifier-only source reads and the existing cooperative sandbox lock. External
administration exclusion still requires injected trusted maintenance verification;
the default denies it. The default inspection adapter refuses before
authority/raw-storage access. `production_inspection()` still always raises
`storage_inspection_unavailable`, including with root/flags/injected evidence.

## Component API and trust boundary

`OneShotInspection(binding, trusted_mount_identity, *, authority,
checkpoint_sink, adapter=None, limits=None, trusted_owner_uid=0, clock=...,
nonce_factory=...).inspect(InspectionRequest(project_id, feature_id, run_id))`
accepts identifiers only. Trusted binding/mount/owner/adapter/sink are
administrative construction dependencies, never project fields or request flags.
An instance is consumed by its first valid attempt; there is no automatic retry.

`InspectionAuthority.source_lease(request, timeout)` returns a context manager
with `SourceLease(cooperative=True, external_admin_excluded=True)`.
`read_run(request, timeout)` reads the trusted ledger by identifiers under that
lease. The controller checks all three request identifiers, durable preparation
nonce/container ownership, terminal stopped outcome, image/quota/backend and exact
upper/work/merged/lower paths. Legacy runs are refused, not reconciled by editing
the ledger. A deep copy protects the original baseline record from helper writes.

The lease must use the existing lock namespace:
`sandbox-<sha256(project_id + '/' + run_id)>.lock`. Its authority must deny
unfinished/held inspections and live source work. **This is only cooperative
exclusion.** It does not stop another Docker socket user or root administrator
starting, deleting or modifying the source. Production use requires an explicitly
owned maintenance window excluding those actors for the entire operation, and
continuing exclusion when effects are held. The boolean injected proof models that
obligation; it does not establish real exclusion.

The callable `CheckpointSink(record)` reserves a unique request/inspection nonce,
rejects conflicting or unfinished/held reservations, and atomically retains each
dedicated inspection checkpoint. It must never update the baseline outcome or
replace source ownership. Coordinator-owned `InspectionLedger` now supplies this
sink without adding a launcher operation or changing baseline records. Calls receive detached snapshots. Sink
writes must be bounded/nonblocking; failure prevents new effects, still attempts
safe stopping/release, and cannot return a successful result. An existing durable
intent remains the recovery authority if a final write fails. No retry algorithm
or second writable operational authority is introduced.

`InspectionAdapter` supplies the following narrow operations, each with a supplied
timeout: `preflight`, `read_source`, `pin_storage`, `handoff`, `create_inspector`,
`verify_inspector`, `start_inspector`, `collect`, `stop_confirmed`,
`release_handoff`. Context entry is included in the command allowance; context
exit must be nonblocking. A real transport must enforce deadlines and reap its
descendants; the in-process component can reject late returns but cannot kill a
hung injected Python function. No injected adapter pass is production qualification.

Preflight requires affirmative **privileged xattr visibility** and the approved
root `MountIdentity(device, inode, mount_id)`. Empty unprivileged `listxattr` is not
proof. The pinned descriptor must match that identity and the configured owner;
the identity is rechecked across handoff and after inspector stopping. Scanning
retains existing fail-closed symlink, mount-crossing, lower-content, OverlayFS
metadata, whiteout, link/device and replacement denials. Only complete raw-upper
checkouts are supported; ambiguous fidelity is refusal, not speculative merging.

## Bounds, inspector and result

Defaults are ceilings, not project-tunable increases:

| Bound | Value |
|---|---:|
| Total work | 60 seconds |
| Reserved cleanup | 20 seconds, shared by stop/recheck/release |
| Each adapter command | 15 seconds or remaining phase time |
| Scan entries / depth | 10,000 / 64 |
| Logical bytes | Recorded source writable-layer quota |
| Collected JSON | 64 KiB |

Cleanup deadline is `min(cleanup_start + 20, work_deadline + 20)`, not a new budget
per operation. Both deadlines and consumed time are checkpointed. Monotonic
timestamps describe this invocation only; they are not M5 restart/resume tokens.

`InspectorSpec` fixes approved local image identity, baseline commit, run branch,
source checkpoint and private nonce. Its modeled effective configuration is UID
10001, read-only root, offline/no ports, no capabilities/privilege escalation,
0.25 CPU, 96 MiB memory/no swap, 32 PIDs, 64 MiB own-layer quota, bounded 8 MiB
tmpfs, and 1 MiB/one-file local logs without compression. The only bind is
read-only/nonrecursive `/retained`, with `rprivate` propagation. A trusted immutable
probe runs Python/Git directly, with configuration/hook discovery disabled; no
repository scripts, OpenCode service, secret broker or worker command is allowed.
Actual immutable probe packaging/delivery remains to implement and pin before
qualification; the component names a fixed probe contract, not new worker assets.

Creation must enforce absence/no-recreate. Its nonce is journaled **before** creation
and returned immutable ID **before** start. `InspectorObservation` must attest that
ID, nonce, full effective configuration hash and pinned handoff token. Unknown or
foreign ownership cannot authorize start or stop-by-name. Ambiguous creation holds
the handoff, not adoption/removal of any container.

Collection requires matching inspector/source/checkpoint/nonce/baseline identities,
integer exit zero, one bounded strict JSON object with exactly the approved fields,
true Git independence/connectivity/ref/read-only/EROFS/offline/socket-denial flags,
and `repository_code_executed: false`. Missing, raw, duplicate, extra, forged,
oversized or boolean-as-integer evidence fails. Only counts, identities, fixed
diagnostics and an evidence hash enter the dedicated journal; no content, paths,
exception text or credential values. Evidence bytes are validated transiently, not
retained by this component. Every result records `qualified: false`.

### Dedicated journal schema v1

Each record contains `inspection_id`, `state`, `request` (three identifiers),
`source_container_id`, `source_checkpoint_sha256`, `inspector_nonce`,
`inspector_container_id`, `started_monotonic`, `work_deadline`, `cleanup_deadline`,
`consumed_seconds`, `stop_confirmed`, `handoff_confirmed`,
`handoff_release_confirmed`, `lease_release_confirmed`, `source_unchanged`, and
allowlisted `result`. Pending source/inspector identities are null, never invented.

States: `preparing`, `source-admitted`, `handoff-intent`, `handoff-ready`,
`create-intent`, `created`, `start-intent`, `collecting`, `stopping`,
`releasing-handoff`; terminal `inspection-blocked`, `inspection-passed`,
`inspection-failed`, `inspection-held`.

Uncertain stopping, handoff release, lease release or journal durability is held.
Handoff release is attempted only with a valid owned receipt and no inspector
creation attempt or positively confirmed stopping. Confirmed stopped inspectors
and evidence remain retained. Keyboard interruption attempts bounded cleanup,
journals the outcome, closes descriptors/lease and propagates the interruption.
An uncatchable process death leaves durable intent/effects held; cleanup/recovery
requires separate administration, not a claimed M5 implementation.

## Proposed privileged mount handoff — not implemented or qualified

Prefer one explicitly administrator-invoked process, not a privileged daemon or
ordinary Coordinator operation. Fixed local socket: `/var/run/docker.sock`;
trusted current root: `/mnt/routine-docker/docker`, classic overlay2/XFS with
project quotas. Ignore inherited Docker contexts, credentials, `DOCKER_HOST` and
project configuration. Bind daemon/root/filesystem/mount identities through trusted
administration; safely open ancestors, allowing only the specifically approved XFS
mount boundary, never arbitrary symlink/bind crossings.

1. Hold the source lease/maintenance exclusion; freshly resolve ledger identity
   and stopped source. Open root and checkout read-only with no-follow descriptors.
   Establish actual privileged `trusted.overlay.*` visibility, scan fidelity and
   bounds; refuse every ambiguous/unsupported tree.
2. Prototype descriptor-based `open_tree(..., AT_EMPTY_PATH | OPEN_TREE_CLONE |
   OPEN_TREE_CLOEXEC)` without recursion. Before attachment, use `mount_setattr`
   to set read-only/nosuid/nodev/noexec and private propagation. Use `move_mount`
   with an empty-path source FD into a root-owned 0700 staging subtree such as
   `/run/opencode-routine-inspection/<nonce>/retained`. Precise kernel support,
   permissions and propagation behavior require real proof; unsupported is denial.
3. Verify staging ownership, inode/device identity and mount flags/identity. Keep
   the descriptor, stage and one-shot process alive while Docker binds only that
   stable staging mount read-only/nonrecursive with `rprivate`. Stage is outside
   Docker's data root, avoiding the raw-root propagation special case. Verify
   daemon mount-namespace visibility and effective inspector mount identity.
   **Never give Docker `/proc/self/fd/N`, another process's proc FD, or `/dev/fd/N`.**
4. Confirm immutable inspector ownership/configuration before start and after
   stop. Recheck source/root identity. Unmount only the receipt-owned staging
   mount after confirmed stop; never modify Docker's data directories or detach
   a live inspector's source. Ambiguity retains mounts/effects and holds dispatch.

This is an injectable `HandoffReceipt` contract, not a statement that these
syscalls or Docker handoff are already working. Staging namespace visibility,
pinning across source pathname swaps, metadata visibility and actual EROFS—not
ENOSPC/permissions alone—are mandatory qualification cases.

## Exact next approvals and finite qualification

**Approval A: privileged inspection qualification only.** Approve the fixed
one-shot helper/probe revision and local image ID; select by immutable IDs one
fresh ordinary and one full-layer stopped fixture with durable preparation fields
(the historical manually inspected fixture must not be silently adopted). Before
execution, record the selected request/container/checkpoint/image IDs and current
daemon/mount identity. Permit privileged read-only ancestor/xattr observation,
descriptor-mount staging under the exact new `/run/.../<nonce>` subtree, and only
the two specified offline inspectors with the bounds above. Permit a finite
administrator-owned XFS metadata sentinel fixture outside Docker's data root to
prove `trusted.overlay.*` visibility and rejection; retain it without cleanup.
No existing container starts, project-byte deletion, quota increases, raw-root
binds, packages/configuration edits, networks, credentials or service installation.

Record positive ordinary/full-layer inspection plus finite negatives: missing
privileged visibility; unexpected mount identity; symlink/mount/path-swap races;
lower-layer/overlay-dependent tree; malformed/extra evidence; foreign inspector
nonce/ID; exhausted work deadline; and unconfirmed stop/release. Compare source
inspection before/after, unchanged quota/identities, descriptor cleanup and actual
EROFS. Safety-negative fixtures are administrator-owned local test trees, never
mutations of retained source data. Retain all failed intents/artifacts. Stop if
maintenance exclusion, source admission or transport safety cannot be established.

**Approval B: separate daemon restart/persistence qualification.** Obtain a
maintenance window and read-only inventory of all existing workloads; any running
non-test workload requires its owner's explicit consent or deferral. Pin daemon
ID/version/root, XFS UUID/mount/project-quota flags, image IDs, source/container
states/quotas, source content observations and host ledger/evidence hashes.
Approve exactly one `systemctl restart docker`, supervised for at most 120 seconds,
without edits to daemon/systemd/fstab/filesystem configuration. The supervisor must
inspect actual daemon/job state after timeout; timing out a client does not prove
restart cancellation. Do not retry/restart sources or reset state on uncertainty.

After restart, require the same root/backend/filesystem/project quotas, approved
images and retained source/container identities/stopped states, unchanged ledger
and evidence, and repeat the two approved safe inspections. Approve one new finite
offline 96 MiB write attempt under a 64 MiB quota; require synchronized
ENOSPC/EDQUOT and retained diagnostics without truncation/freeing bytes. Failure
holds qualification and calls for a separately approved intervention, not silent
rollback/deletion. This proves daemon restart persistence only—not boot persistence,
general recovery, production inspection enablement, M2 acceptance or Gate A.

## Offline validation

S1 local validation: **61 retention tests pass** (24 existing plus 37 new).
Complete offline suite: **229 passed, 18 live tests skipped** (247 total).
All three live image opt-ins were explicitly unset. No privileged/raw-storage,
Docker inspector, image build, daemon restart or external access was performed.

Run without any live image opt-ins:

```sh
python3 -B -m unittest discover -s linux/opencode-routine/tests -p 'test_m2_retention*.py' -v
python3 -B -m unittest discover -s linux/opencode-routine/tests
```

Local fixture/injected passes establish component ordering, bounds, dedicated
checkpoints, ownership refusal, evidence filtering and cleanup semantics only.
Privileged visibility, mount transport, external-administration exclusion and
restart persistence remain open until separately approved real qualification.
