# OpenCode routine — host launcher

**Experimental checkpoint, not the active S0 implementation.** W1 authorization/claims
are accepted. W2 independent-clone preparation, lifecycle and injected OpenCode
V2.0.22 adapter are assembled; independent review/verification and separately
approved real qualification determine readiness. W2 is not accepted, and W3–W9
are not authorized. The active one-slice plan is `docs/workflow-plan.md` on
`main`; the earlier W1–W9 sequence and its evidence are [package history](docs/README.md),
not the current build order.

This Linux-only Python 3.11+ launcher owns immutable planning authorization,
exclusive claims, process-scoped Coordinator leases and one durable JSON ledger.
Each local run gets an independent clone, not a worktree or shared Git metadata.
Local execution is **not a sandbox**: neither clones nor role permissions prevent
same-user access to host files, credentials, networks or processes. Use only
explicitly approved trusted fixtures at this stage.

Sandboxing is deferred to a separate project. Existing M1/M2 code, records,
qualification evidence and host setup are preserved; no sandbox request can fall
back to local execution. Product implementation/delegation, verified integration,
PR management, comprehensive interruption recovery and QA remain later milestones.
No third-party Python dependencies are required.

## W1/W2 local interfaces and approval boundaries

- Local profiles use version **4**, `execution: "trusted-local"`; approval manifests
  use version **2** with the same execution identity. Historical sandbox profiles
  and records cannot authorize local runs.
- Trusted administration approves the exact planning package, baseline commit/ref,
  prompt/skill bundle, reviewed API/configuration bytes and fixture evidence. A
  separate single-slice dispatch authorization limits what the Coordinator may
  claim. The local bundle is distinct from the historical worker-image `bundle-id`.
- Claimed runs expose typed `local-prepare`, `local-fixture-check` and `local-stop`
  operations, plus status. Callers supply identifiers, not checkout paths, commands,
  service URLs, configuration or authentication values. For an already authorized
  and claimed local run:

  ```json
  {"operation":"local-prepare","run_id":"run-01"}
  {"operation":"local-fixture-check","run_id":"run-01"}
  {"operation":"local-stop","run_id":"run-01"}
  ```

- Preparation journals intent, exclusively creates the run artifact, exports the
  exact Git baseline configuration-blindly, clones it and retains a hash-bound
  handoff containing the full planning inputs, criterion mapping and frozen bundle.
  Collisions and interruptions hold the run; they are not overwritten or resumed.
- Run artifacts live below
  `$XDG_STATE_HOME/opencode-routine/artifacts/local-<run-key-hash>/`, with `checkout/`,
  `handoff/` and `evidence/`. The ledger remains the only operational authority.
  Byte/deadline limits are not disk or host-resource containment.
- Fixture execution requires approved effective configuration, parent/child
  directory routing, permission/delegation observations and owned-process stopping.
  The adapter accepts injected transport/discovery/observer interfaces; it does not
  discover/start a service or connect on its own. Without approved assembly the
  runtime path fails closed. Deterministic observations do not establish real gates.
- `local-stop` persists a stopping-only request without waiting on the lifecycle
  lock. The owning driver collects allowlisted diagnostics before stopping registered
  work. Missing ownership or unconfirmed stopping holds the run and preserves
  artifacts; the shared service and unrelated work must not be terminated.
- `local-fixture-passed` is not slice verification/integration and does not unlock
  dependencies. The real two-clone routing/configuration/stopping exercise needs
  separate approval after deterministic assembly/review. Ordinary project execution,
  installation, infrastructure mutation, GitHub writes and repository commits are
  not authorized by the current W2 source/test approval.

### Daemon-free validation

```sh
env -u OPENCODE_ROUTINE_TEST_IMAGE -u OPENCODE_ROUTINE_COMPONENT_IMAGE \
    -u OPENCODE_ROUTINE_STORAGE_IMAGE \
    TMPDIR=/tmp/opencode PYTHONDONTWRITEBYTECODE=1 \
  python3 -B -m unittest discover -s linux/opencode-routine/tests -v
```

Local coverage is in `tests/test_w1*.py`, `tests/test_w2*.py` and
`tests/w2_fixture.py`. Historical tests remain regressions, not current local
runtime qualification. Earlier identities/results are in the historical
[W1–W9 plan](docs/workflow/implementation-plan.md); the current offline test
result is a checkpoint observation, not W2 real qualification.

## Historical M1/M2 sandbox interfaces — retained, deferred

The documentation below preserves the earlier sandbox path and its recorded
checkpoint counts. It does not define the current workflow-first milestones or
authorize new live sandbox qualification. M1 was accepted historically; M2 and
Gate A were not. The offline baseline, proxy and gated environment components
remain separate from the local interfaces above.

### M2 parallel implementation checkpoints

S1 adds a bounded one-shot retained-inspection lifecycle and dedicated atomic
ledger records; production inspection still always refuses. N1 adds injectable
Docker network/proxy transactions, nftables batches and identity-bound DNS/rule
readbacks. C1 adds bounded service lifecycle and an explicitly granted file-backed
credential source. Combined offline checks use the existing scoped delivery
primitive and one host-ledger sink; provider keys are not resolved by service checks.

These are implementation components, not live isolation qualification. The default
`environment-check` remains disabled; no profile or Coordinator flag enables it.
Provider preparation is secret-free and **non-executable**: actual OpenCode provider
configuration remains blocked pending authoritative V2.0.22 configuration evidence
and an approved trusted mapping. No M3 or later milestone has started.

See the [sandbox history](docs/README.md) for the M2 interface checkpoint and
storage/network/services proposals, including remaining blockers and separate approvals.

## Install separately from project setup

From the dotfiles root, inspect the Stow dry run before installing:

```sh
stow -n -v -t ~ -d linux opencode-routine
stow -t ~ -d linux opencode-routine
opencode-routine --help
```

Ensure `~/.local/bin` is on `PATH`. Installation does not onboard or mutate a
project, start a service, provision Docker, or install OpenCode. The package can
also be invoked directly with `linux/opencode-routine/.local/bin/opencode-routine`.

## Planning contract v1

The trusted user prepares and approves these project-relative inputs:

- `.opencode/routine/project.json`: versioned environment profile.
- `.opencode/routine/features/<feature-id>/approval.json`: feature manifest.
- The UTF-8 spec and tickets referenced by the manifest, anywhere below the project
  root except `.git`. Input paths must be normalized, distinct and not symlinked.

Each spec criterion has a unique marker, such as
`<!-- criterion: AC-1 -->`. The spec manifest lists **all** those criterion IDs;
each ticket explicitly maps its applicable IDs. This resolves references, not
semantic completeness: independent full-spec review remains a later gate.

Example approval manifest (replace every hash with the actual identity):

```json
{
  "version": 1,
  "feature_id": "example",
  "spec": {
    "path": "planning/example/spec.md",
    "sha256": "<sha256 of exact spec bytes>",
    "criteria": ["AC-1", "AC-2"]
  },
  "tickets": [
    {
      "slice_id": "01",
      "path": "planning/example/01.md",
      "sha256": "<sha256 of exact ticket bytes>",
      "criteria": ["AC-1"],
      "dependencies": []
    },
    {
      "slice_id": "02",
      "path": "planning/example/02.md",
      "sha256": "<sha256 of exact ticket bytes>",
      "criteria": ["AC-2"],
      "dependencies": ["01"]
    }
  ],
  "profile_sha256": "<sha256 of exact project.json bytes>",
  "bundle_sha256": "<approved historical bundle identity; worker assets for M2>",
  "baseline": {
    "commit": "<exact 40- or 64-character lowercase Git object ID>",
    "branch": "refs/heads/features/example"
  }
}
```

Example profile (resource values must be selected and approved per project;
these are illustrative, not launcher defaults):

```json
{
  "version": 1,
  "commands": {
    "setup": [],
    "checks": {
      "test": {"argv": ["python3", "-m", "unittest"], "timeout_seconds": 60}
    }
  },
  "services": [],
  "mounts": [],
  "network": {"allowed_domains": []},
  "credential_refs": [],
  "providers": [],
  "resources": {
    "cpus": 1, "memory_mb": 512, "pids": 64,
    "disk_mb": 1024, "log_mb": 16, "command_seconds": 60
  },
  "budgets": {
    "slice_seconds": 3600, "inactivity_seconds": 600,
    "integration_seconds": 1800, "repairs": 2
  },
  "qa": {"kind": "none", "start": null}
}
```

Unknown fields are rejected. Commands are argv arrays plus positive deadlines,
never host-executable requests. Checks require at least one named command.
Optional services use `{ "id": "database", "image": "<approved image>" }`.
Provider entries use `{ "id": "openai", "credential_ref": "model-access" }`, with
the reference also listed under `credential_refs`; never put secret values here.
Network entries are explicit DNS names without wildcards or IP literals.
Optional mounts are project-relative **files**, read-only, with targets strictly
below `/inputs`; they are validated, not mounted in M1. QA kinds are `none`,
`command` or `browser`; the latter two require a `start` command object.

M1 pins declared bundle/baseline identities. M2's offline baseline materializes an
independent checkout of the exact commit, validates the packaged worker asset
fingerprint and requires a pinned image/release. Full Git ancestry gating, actual
OpenCode V2 qualification, credentials and revision-specific readiness remain later
validation obligations.

## Authorization, claim and status

Only the trusted user-facing administration surface accepts a project root:

```sh
opencode-routine authorize --project my-project --feature example --root /absolute/project
opencode-routine status --project my-project --feature example
opencode-routine coordinate --project my-project --feature example --coordinator coordinator-1
```

`authorize` is the execution authorization of already reviewed artifacts; it is
not an agent's permission to approve its own plan. Capture the returned
`authorization_id`. `coordinate` outputs one `coordinator_opened` JSON object,
then accepts newline-delimited JSON on stdin while holding an exclusive OS lock:

```json
{"operation":"claim","slice_id":"01","run_id":"run-01","authorization_id":"<returned sha256>"}
{"operation":"status"}
```

Every request produces one JSON response. Errors use
`{"error":{"code":"...","message":"..."}}`. A malformed request does not end
the lease. EOF closes it cleanly. No paths, commands, Compose fragments or
authorization/integration operations are accepted through this interface. M2's
`baseline` operation is documented below.
The offline `proxy-check` and gated `environment-plan`/`environment-check`
operations are documented below. The future OpenCode
adapter must expose only this narrow interface, not shell
access to the trusted administration CLI.

Repeating the same run request returns the original run, including its original
timestamp. Run IDs are unique within a project and cannot be reused with changed
feature/slice/authorization/Coordinator inputs. A second run for an already claimed
slice fails. Feature IDs cannot be reauthorized with changed immutable inputs;
use a new approved feature identity. Spec, ticket, manifest or profile drift is
rejected even when the caller edits their declared hashes to match.

Dependencies require **verified integration**, not a claim or a baseline pass.
Integration is not implemented, so dependent slices remain unavailable. It never
silently claims alternative work. Status exposes eligibility and waiting reasons
without writing back to planning documents.

## State and interruption

The only operational authority is
`$XDG_STATE_HOME/opencode-routine/ledger.json` (default
`~/.local/state/opencode-routine/ledger.json`). It includes retained snapshots of
the approved planning package and run records. The state directory is `0700`;
ledger and stable lock files are `0600`. Unsafe ownership, permissions, symlinks
or hardlinked files are rejected. Keep this directory outside every project and
never mount it in a worker.

`ledger.lock` serializes read-modify-write, separate from the per-feature
Coordinator locks. Updates synchronize the temporary file, replace the ledger
atomically, then synchronize the directory. Lock files are never removed or
replaced. On process interruption the kernel releases the lease, but a persisted
Coordinator record prevents implicit takeover (`recovery_required`). Deliberate
recovery is deferred to M5; **do not manually reset the ledger**.

Private file modes do not restrict other processes running as the same host user.
Actual worker denial requires the unmounted container boundary and its M2 probes;
M1 tests alone are not evidence of container, network or credential isolation.

## Validation

From the dotfiles root:

```sh
env -u OPENCODE_ROUTINE_TEST_IMAGE -u OPENCODE_ROUTINE_COMPONENT_IMAGE \
    -u OPENCODE_ROUTINE_STORAGE_IMAGE \
    TMPDIR=/tmp/opencode PYTHONDONTWRITEBYTECODE=1 \
  python3 -B -m unittest discover -s linux/opencode-routine/tests -v
```

Fixtures live under `/tmp/opencode` and are removed after each test. Tests cover
immutable authorization, malformed profiles/graphs/criteria, planning retention,
duplicate claims, simultaneous cross-feature process updates, dependency holds,
private storage, the typed CLI, a real competing process lease, Stow installation
into a temporary home, and process termination around each atomic-write checkpoint.
By default no production project, live OpenCode service, Docker environment or
GitHub repository is used. The M2 smoke test below is explicitly opt-in.

## M2 — offline sandbox baseline

This is a first end-to-end **baseline** path, not completion of M2 or permission
to implement a product slice. Profiles asking for egress, services,
providers or credentials are rejected with `policy_unavailable`. Completing and
qualifying the egress proxy/firewall, service and credential policy is still required;
there is no fallback to broad networking or inherited host integrations.

Keep the approval manifest at version 1. To opt into a baseline launch, approve a
**profile version 2** with the same fields as v1 plus:

```json
{
  "version": 2,
  "runtime": {
    "image": "sha256:<exact 64-character local Docker image ID>",
    "opencode_version": "2.0.22"
  }
}
```

The worker image must already exist locally, include the shipped worker assets and
the verified V2.0.22 binary, and have matching `routine.bundle-sha256` and
`routine.opencode-version` labels. Launch never builds or pulls images. Run
`opencode-routine bundle-id` to obtain the current local worker asset fingerprint;
this does not initialize state or build an image. An existing authorization is
immutable: changing the profile requires a new approved feature identity.

### Approved read-only file inputs

Profile v2 accepts regular-file inputs with an explicit content hash:

```json
{
  "mounts": [
    {
      "source": "fixtures/sample.data",
      "target": "/inputs/sample.data",
      "read_only": true,
      "sha256": "<64-character SHA-256 of the approved file bytes>"
    }
  ]
}
```

Sources must be project-relative regular files, with no symlink ancestors or
hardlinks. Targets must be distinct, non-overlapping file paths below `/inputs`.
Directories, devices, sockets, FIFOs, writable inputs and outside-project sources
are not supported. Inputs are approved development/test data, **not** a means to
inject production data or credentials; credential handling remains unimplemented.

Authorization records ordered source/target/hash/size metadata, never raw input
bytes in the ledger. Claim and preparation recheck the content. Preparation makes
new, bounded, read-only copies under the private per-run `handoff/mounts/` directory;
Compose mounts **these snapshots**, never live project files. Subsequent source
edits do not alter a prepared snapshot. Input copies, planning context and Git
bundle share a preparation-byte cap equal to `resources.disk_mb`. Hashing/copying
checks deadlines; source drift, unsafe paths or budget exhaustion prevent dispatch.

The worker checks hash, size and effective read-only status at both `/handoff`
and `/inputs` before cloning or running setup. Evidence v2 adds only the verified
input metadata. Missing/modified/extra input evidence cannot establish a pass;
raw input bytes are not exported. The bounded live component test checks actual
snapshot readability and write denial. Broader production-path qualification of
approved-input retention remains required.

### Approved image preparation (separate administration)

The recipe is installed at `~/.local/share/opencode-routine/worker/Dockerfile`.
Prepare a **temporary build context outside the project** containing exactly the
four shipped assets (`Dockerfile`, `worker.py`, `opencode.json`, `proxy.py`) and a separately
verified Linux OpenCode V2.0.22 binary named `opencode`. Use an approved
Debian-family base image pinned by registry digest and the binary's verified hash:

```sh
docker build \
  --build-arg BASE_IMAGE='<approved-image>@sha256:<approved-digest>' \
  --build-arg OPENCODE_SHA256='<verified-binary-sha256>' \
  --build-arg BUNDLE_SHA256='<opencode-routine bundle-id value>' \
  --iidfile '<temporary-context>/worker.iid' \
  '<temporary-context>'
```

Use the resulting image ID in the approved profile; use the same asset fingerprint
in the feature manifest. This recipe installs tools **inside the image**, not on
the host. The recipe has been built and its service-component test passes; full
baseline/storage qualification is still incomplete. Do not
copy an entire home, project, Docker configuration, SSH agent or credentials into
the context. No automatic installation or privilege escalation is provided.

Docker must enforce writable-layer `storage_opt.size` quotas. The current path
admits only classic overlay2 on XFS, with project quotas supported at creation.
The former containerd `overlayfs` backend wrote 96 MiB under a purported 64 MiB
limit and remains rejected with `disk_quota_unavailable`. The user-approved
migration now uses `/mnt/routine-docker/docker` on a 50 GiB file-backed XFS
filesystem with project quotas. A finite non-root 96 MiB attempt fails with ENOSPC
at 67,043,328 bytes under a 64 MiB cap; the actual offline baseline smoke test and
stopped-clone inspection pass. See [M2 qualification history](docs/sandbox/m2-qualification.md) for exact evidence.
An entirely full layer prevents Docker from creating its archive mount directory.
Evidence collection now uses the bounded log API without mounting that layer;
read-only inspection of the controlled full fixture now passes through a separately
approved narrow raw-layer bind. Production-safe inspection/recovery remains
unqualified. Do not change storage
configuration further or remove limits without separate approval. Production-path
resource/failure rechecks and broader persistence qualification remain required.
Preflight also requires cgroup v2 and affirmative Docker CPU CFS, memory, swap and
PID-limit support; missing/disabled capabilities return `resource_limits_unavailable`.

### Launch and retain

After the authorized slice has been claimed, use the same Coordinator lease:

```json
{"operation":"baseline","run_id":"run-01"}
```

The host exports objects using a **fresh, sanitized bare Git directory**, never the
source repository's configuration, hooks, fsmonitor, helpers or replacement refs.
Linked-worktree metadata and object alternates are rejected in this first path.
The worker independently clones the bundle inside its own quota-bounded writable
layer. No host repository/Git metadata or writable host directory is mounted.

Generated Compose configuration grants only a read-only, run-specific `/handoff`
and any approved file snapshots below `/inputs`,
uses UID 10001 with no capabilities, no privilege escalation, no shared host PID
namespace, **no networking**, no published ports, fixed CPU/memory/PID/disk limits
and bounded Docker logs. The effective configuration passes `docker compose config`
locally, but that does not establish enforcement.

The worker validates input snapshots, Git bundle, profile and packaged asset identities, then
starts its own `opencode serve` on container loopback. The foreground server's
generated password is read from its private startup log and used only in the CLI
request environment; it is never exported as evidence. Approved setup/check argv
arrays are quoted and submitted through **that service's shell API**, with shell
IDs, exits and deadlines recorded. The service's configuration location is the
root-owned `/control`, outside the checkout, with root-owned global configuration
at `/opt/routine/config`, so unapproved repository `.opencode`
plugins/MCP configuration are not discovered by the baseline service. Actual
service tool-locality, independent clone and repository-plugin denial now pass in
the actual offline baseline smoke test; broader failure qualification remains open.

CLI API requests share each command's deadline, rather than receiving an unrelated
15-second allowance. Known shell commands are cancelled within a separate maximum
two-second cleanup window bounded by the total runtime. Late-observed success is a
timeout, not a pass. Ambiguous creation or failed cancellation fails the baseline;
service/container supervision remains the final stopping boundary.

Only a strict evidence allowlist is exported: exact input/run identities, service
identity, approved input hashes/sizes, command argument hashes, shell IDs, exits
and bounded output-page hashes.
Raw output, command strings, exception text and service logs remain in the retained
container; they are **not** exported using speculative regex secret redaction.
Evidence tar data is bounded and read without extracting any paths, links or devices.
The current worker additionally emits exactly one `routine_evidence` JSON envelope
on stdout, even if ENOSPC prevents the local evidence write. The adapter parses the
entire bounded log stream and applies the same evidence validation; it never scans
for a convenient tail/marker or accepts duplicate/raw records. Only an empty log
stream falls back to archive collection for older approved images. No file deletion
or quota increase is performed to collect evidence.

Before creation the adapter checks for a retained named container. Compose uses
`create --no-recreate`, never an `up` that could replace an old checkout. A private
per-preparation nonce must match before start/stop, which address the verified
immutable container ID. Collisions or changed IDs hold the run; pre-existing
containers are not adopted, replaced or stopped.

Operational run states advance through `preparing`, `starting`, `running`, then
`baseline-passed` or `sandbox-failed`. `baseline-passed` is not ready-for-integration
and does not unblock consumers. Preparation begins the recorded total budget;
the container also enforces that deadline. Repeated completed requests return the
same result. In-progress/held records require deliberate recovery, never a relaunch.
The launch nonce is durably recorded before creation, and the verified container ID
before `running`. A missing creation ID cannot pass. Older retained runs without
these fields are not implicitly eligible for future raw-layer inspection; do not
manually rewrite their ledger records to add ownership.

The launcher stops and confirms the container after collection, retaining its
independent checkout and raw diagnostics. An unconfirmed stop yields `sandbox-held`,
not completion. Host input snapshots and approved evidence are retained below
`$XDG_STATE_HOME/opencode-routine/artifacts/<artifact-id>/`; only the `handoff`
subdirectory and files within it are mounted, never the ledger/locks. No automatic
`down`, `rm`, `prune`
or cleanup is performed.

### M2 validation and remaining work

#### HTTPS proxy component (not enabled for worker egress)

`proxy.py` is included in the immutable worker asset fingerprint/image. It is a
container-only HTTPS `CONNECT` component, **not** an enabled networking mode.
`baseline` still rejects nonempty egress/service/provider/credential requests and
generates `network_mode: none`. No host firewall rules or networks are provisioned.

The component accepts only exact approved lowercase DNS names on port 443, with
an unambiguous HTTP/1.1 CONNECT/Host pair. It rejects bodies, authentication headers,
IP literals, wildcards and local names. Each connection resolves once in a
killable/reaped subprocess; **every** returned address must be public/native
unicast. Special-use/transition exclusions are explicit across Python versions.
Connections dial a validated numeric address and recheck the actual peer, avoiding
a second DNS lookup or fallback to a private address. The initial TLS ClientHello
must expose exactly one matching SNI name; plaintext, absent/different SNI and ECH
are denied before any payload is forwarded.

The container entry point is `python3 -B /opt/routine/bundle/proxy.py <policy-file>`.
The offline launcher check generates/mounts that policy read-only; callers cannot
pass policy files through the typed Coordinator interface. Production egress
dispatch remains disabled. Its exact fields are
`allowed_domains` (list) and positive integer `max_connections`, `request_seconds`,
`idle_seconds`, `tunnel_seconds`, `max_tunnel_bytes`. Duplicate JSON keys fail.
The listener is IPv4 port 3128; production must confine it to its own environment's
worker network, never publish it on the host. Request/DNS/dial/ClientHello share a
deadline. Relay lifetime, per-direction idle/drain time, aggregate bidirectional
bytes and admitted connections are bounded; failure cancels/reaps sibling tasks.
No requests, tunneled bytes, credentials or exception details are logged.

This is a **transport-endpoint** filter, not TLS interception or encrypted HTTP
Host/URL validation. Shared-endpoint domain fronting and alternate routing inside
approved services are unresolved qualification risks; do not claim that matching
CONNECT/SNI alone proves all application destinations are approved. Plain HTTP,
non-443 dependency transports, ECH and legacy TLS are currently unsupported.
Before enabling egress, qualify actual approved endpoints and address those risks,
add the internal per-environment network and host firewall (including direct
bypass, host/LAN, IPv6 and cross-slice denials), and integrate lifecycle/evidence.

Twenty-nine daemon-free proxy tests exercise parsing, DNS rebinding, numeric/peer
pinning, TLS fragmentation, a real Python TLS ClientHello, limits, cancellation
and killable DNS. The opt-in image probe uses a read-only root, bounded RAM/cgroups
and **no networking except loopback**. Its resolver and upstream peer identity are
injected: successful byte relay is not real approved external-access proof. It
exports only boolean observations/identities, never the payload canary, and retains
the stopped container. The same `OPENCODE_ROUTINE_COMPONENT_IMAGE` opt-in below
runs this probe as well as the existing service/resource probes.

#### Run-scoped offline proxy policy and lifecycle check

Profile v2 optionally accepts explicit proxy limits under `network.proxy`. There
are **no default policy limits**; approving these changes requires a new feature
identity when an existing authorization already pins the profile:

```json
{
  "network": {
    "allowed_domains": ["api.example.com"],
    "proxy": {
      "max_connections": 4,
      "request_seconds": 5,
      "idle_seconds": 10,
      "tunnel_seconds": 30,
      "max_tunnel_bytes": 1048576
    }
  }
}
```

Values are illustrative, not launcher defaults. All limits must be positive
integers; connections cannot exceed the profile's PID limit, request time cannot
exceed its command limit, and all proxy time limits must fit its slice budget.
Policies exceeding the proxy's 64 KiB input limit are rejected.

After claiming a run, the same Coordinator can request:

```json
{"operation":"proxy-check","run_id":"run-01"}
```

This is an **offline component check**, not a product launch or egress grant.
It prepares a private run-specific policy/Compose document, pins the approved
image, bundle, profile and policy hash, and mounts only the generated policy file
read-only at `/policy/proxy.json`. The proxy has a read-only root, fixed approved
CPU/memory/PID/log limits, no credentials, no worker checkout, no capabilities,
no published ports and `network_mode: none`. It creates no environment network
and applies no firewall rules. It does not use a writable-layer quota and **cannot
substitute for the disk-enforced baseline**.

Readiness validates effective container configuration, actual asset/policy hashes,
read-only policy status, UID and loopback-only interfaces. An invalid loopback
request must be denied; no DNS lookup, approved upstream connection or payload
relay is used. Healthy status observed after the deadline is not a pass.

The ledger's `run.proxy` advances through `preparing`, `starting`, `ready` and
`stopping`, then `proxy-check-passed` or `proxy-check-failed`. Stop uncertainty or
a pre-existing named container produces `proxy-held`; the launcher never adopts,
replaces or stops that pre-existing container. Duplicate completed checks return
their original result. Interrupted/held checks require deliberate recovery and
block baseline dispatch. The check shares the run's baseline lock and starts its
slice budget at preparation; subsequent baseline preparation cannot reset it.
The check itself is bounded by `resources.command_seconds`, plus a separate
maximum 20-second stopping/confirmation window.

The slice stays `claimed`, consumers remain blocked, and `status` exposes the
proxy checkpoint separately. Retained policy, generated Compose and allowlisted
evidence live under the private state artifact directory; stopped containers are
retained. Evidence explicitly records `egress_enabled: false`,
`approved_external_access_qualified: false` and `host_firewall_qualified: false`.
Baseline still rejects nonempty domains/services/providers/credential references.

Daemon-free lifecycle tests cover policy validation, immutable inputs, duplicate
requests, ambiguous creation, readiness failure/deadlines, effective configuration
drift, stop uncertainty, interruption and unsafe artifact paths. The explicit
`OPENCODE_ROUTINE_COMPONENT_IMAGE` opt-in also exercises the real launcher with a
valid policy and a modified-policy negative case, retaining identities/evidence
under `/tmp/opencode/routine-m2-proxy-lifecycle-*/`. No real egress is qualified.

#### Profile v3 — gated environment policies and component lifecycle

Profile v3 is an opt-in **planning contract**, not an enabled online runtime. The
approval manifest stays at version 1, and profiles v1/v2 remain supported unchanged.
New profile bytes require a new approved feature identity; this is not an automatic
migration of existing authorizations. Baseline and offline proxy dispatch still
require profile v2; v3 cannot fall back to them or bypass the disk gate.

V3 retains the v2 fields and pinned runtime, but requires these richer contracts:

- `network`: exact `allowed_domains`, explicit `proxy` limits, and `dns_servers`.
  Resolver addresses must be distinct public native IPv4 addresses. Nonempty
  domains require nonempty resolvers; offline profiles cannot grant resolver egress.
  The generated proxy policy must fit its 64 KiB input limit.
- `services`: exact `id`, pinned local `image`, non-root numeric `user` (`UID:GID`),
  distinct TCP `ports`, `readiness` command, full `resources`, and `tmpfs` list.
  Each tmpfs entry has exact `target`/`size_mb` fields; targets must be normalized,
  non-overlapping and outside protected configuration, device and credential paths.
  Total tmpfs must fit that service's approved disk budget. The runtime contract
  requires a read-only service root, declared tmpfs only and no host port publishing.
- `providers`: exact `id`, `credential_ref`, and nonempty `domains`, all of which
  must already be approved network domains. This pins permitted provider routing,
  **not** an implemented OpenCode provider configuration/authentication adapter.
- `credential_bindings`: explicit consumer-scoped development/model grants. Secret
  values, host paths, environment injection requests and production purposes are
  forbidden. All `credential_refs` must be used; providers receive only their
  declared reference. Example bindings (all values require project approval):

```json
[
  {"ref":"database-access","consumer":"service:database","purpose":"development","max_bytes":128},
  {"ref":"model-access","consumer":"provider:openai","purpose":"model","max_bytes":128}
]
```

The generated file targets are fixed, consumer-specific paths such as
`/run/credentials/service/database/database-access` and
`/run/credentials/provider/openai/model-access`. Each size limit is positive and
at most 64 KiB. Model references cannot be repurposed as service-development grants.
Labels/grants do not establish that a real source is non-production: a separately
approved trusted broker must enforce that boundary. No broker/source is configured.

After claiming a v3 run, use only its identifier:

```json
{"operation":"environment-plan","run_id":"run-01"}
{"operation":"environment-check","run_id":"run-01"}
```

`environment-plan` retains a private, immutable, request/profile/bundle/baseline-
bound `plan.json` and its hash under the host artifact directory. It is **not**
executable Compose or an installed firewall. Its scoped topology permits only
worker → proxy:3128, worker → explicitly declared service TCP ports, and proxy →
public IPv4:443 / approved DNS resolvers:53. Services have no outbound permission.
The external network/proxy are omitted when no egress is requested. Replies must
belong to authorized flows; host/LAN, cross-environment, direct worker egress,
forwarded worker/service DNS, IPv6 and undeclared same-bridge traffic are denied.

The policy identifies required enforcement points: host input, forwarding before
Docker's accept rules, same-bridge traffic and container DNS. Effective container
interface identities, all host addresses and connected routes must be verified by
the future backend; public-address classification alone is not host/LAN isolation.
The pure `allows_flow` helper tests the policy model, **not** real packet filtering
or encrypted HTTP routing. Production firewall/backend and DNS-bypass handling
remain unimplemented and unqualified; Compose separation is not substituted for them.

`environment-check` currently records **`environment-blocked` / `policy_unavailable`**
before creating any network, applying rules, reading credentials or starting a
component. This gate is unconditional in the production adapter: no profile field,
Coordinator flag or fake test result can enable it. The slice stays `claimed`,
consumers remain blocked, and `status` exposes the environment record separately.

The controller is exercised with injected test adapters: preflight → create empty
networks → enforce policy → stage only service credentials → start/verify proxy
and services → stop in reverse order → remove only owned credential files after
confirmed stopping. Provider credentials are deferred until a future worker
requires them; proxies receive none. Attempts are journaled before side effects.
Interrupted/uncertain environments require deliberate recovery and block baseline
or proxy dispatch. Completed requests are idempotent. Preparation shares the
baseline/proxy lock and slice deadline; per-command/service-readiness deadlines
reject late success, with a separate bounded 20-second stopping window.

The broker-file primitive accepts bounded erasable buffers, creates private
consumer-scoped read-only files exclusively, exports references/permissions only
(no values, actual secret lengths or secret hashes), and refuses cleanup of replaced/linked files.
Tests use fake bytes only. Returned mutable buffers are overwritten; unlinking a
file is **not** revocation or proof that every memory/disk/container copy is erased.
Uncertain stopping retains private files for deliberate recovery, not automatic
deletion beneath a live consumer. Real broker delivery, token revocation, provider
configuration and service Docker execution still need implementation/qualification.

The new daemon-free suite is `tests/test_m2_environment.py`. It provides contract
and lifecycle evidence only; it starts no services and accesses no real secrets.

#### Qualification and open gates

The built image and positive/negative qualification identities are recorded in
[M2 qualification history](docs/sandbox/m2-qualification.md). A separate component
test can safely exercise the real service on this host without admitting an
unbounded production checkout:

```sh
OPENCODE_ROUTINE_COMPONENT_IMAGE='sha256:<approved-local-image-id>' \
  python3 -B -m unittest discover -s linux/opencode-routine/tests -v
```

It uses a read-only root and bounded tmpfs, checks actual cgroup limits, locality,
host/LAN/IPv4/IPv6 denials, approved snapshot hashes/write denial and hash-only
output, host ledger/lock denial and timed-out setup descendant cleanup, and retains inspection/evidence
under `/tmp/opencode/routine-m2-component-*/`. It is **not** a fallback storage mode
for a baseline run and does not establish checkout retention or approved egress.

The same explicit opt-in runs finite CPU/memory/PID/tmpfs exhaustion and Docker log
rotation probes in separate read-only-root containers. They retain exact probe,
image and result identities under `/tmp/opencode/routine-m2-resources-*/`. Without
opt-in, those tests skip. Tmpfs ENOSPC is **not** production disk-quota proof, and
bounded log retrieval is not a direct on-disk audit of daemon/application logs.

The normal test command also exercises the adapter with deterministic fakes,
real configuration-blind Git export with malicious hook/config canaries, bounded
host subprocesses, evidence injection/archive rejection and daemon-free Compose
configuration validation. These are **not** container isolation evidence.

After separately approving/preparing an image and arranging Docker access, an
explicitly opted-in **smoke test** can run the real container-local baseline:

```sh
OPENCODE_ROUTINE_TEST_IMAGE='sha256:<approved-local-image-id>' \
  python3 -B -m unittest discover -s linux/opencode-routine/tests -p test_m2.py -v
```

It includes independent Git metadata, filesystem/tool-locality, network-interface,
malicious repository plugin and secret-output canaries. It deliberately retains
the stopped container; fixture host files are disposable. This smoke test is not
the complete M2 qualification suite.

Retained storage tests can be run separately (no daemon restart or setup mutation):

```sh
OPENCODE_ROUTINE_STORAGE_IMAGE='sha256:<approved-local-image-id>' \
  python3 -B -m unittest discover -s linux/opencode-routine/tests -p test_m2_storage.py -v
```

These keep the entire private host fixture/ledger/artifact tree and stopped
containers under `/tmp/opencode/routine-m2-storage-*/`. Eight live cases cover a
completely full layer, a pre-existing-container collision, setup failure, setup
timeout, state denial/ordinary checkout retention and actual CPU/memory/PID limits
through container-local service commands. Memory enforcement additionally requires
an independent observed host cgroup OOM-kill event; the test does not assume the
kernel kills only the allocation child. A stopped failure stays failed if the
service/client is killed. Ten daemon-free tests cover the evidence transport and
ownership boundaries. Normal suite: **192 passed, 18 live tests skipped**; all
opt-ins: **210 passed** at the documented revision.

`tests/fixtures/full_layer_inspection.py` is the read-only probe used for that
one-off approved inspector, not a launcher command or ordinary-worker entry point.
It verifies Git anchors/object connectivity, the retained marker/fill file and
actual `EROFS` write denial. Raw upper directories are not generally merged
checkouts; safe source resolution, symlinks, lower layers and whiteouts still need
production qualification. The single-fixture approval does not enable new worker
mounts or a general recovery API. See [M2 qualification history](docs/sandbox/m2-qualification.md) for the exact
read-only bind, Docker's required `rslave` propagation and retained evidence.

`routine/retention.py` adds admission/read-only descriptor primitives and 24 local
contract tests in `tests/test_m2_retention.py`. These require durable stopped-run
ownership, a trusted daemon/storage root and strictly bounded graphdriver paths.
The scanner rejects lower-layer checkout content, symlink ancestors, mount
crossings, OverlayFS metadata/whiteouts, links/devices and exhausted scan bounds.
Pinned descriptors do not switch checkouts when a pathname is replaced. This is a
conservative raw-upper-only subset, not merged-filesystem reconstruction.

Production inspection is unconditionally disabled: a privileged trusted-root/xattr
observer and qualified pinned-descriptor Docker mount transport still need separate
approval. Local fixture tests cannot prove privileged metadata visibility or safe
mount handoff. No Coordinator operation/profile flag enables this component; the
ordinary-worker mount policy is unchanged.

M2 remains open pending production-safe retained-checkout inspection/recovery, restart persistence,
privileged source validation/mount handoff, credential handling,
approved access through the egress policy, and blocked host/LAN/IPv6/cross-slice
access. M3 must not be considered accepted before those obligations are satisfied.

API/configuration references: [V2 configuration](https://opencode.ai/v2/docs/config),
[plugin discovery](https://opencode.ai/v2/docs/plugins),
[CLI](https://opencode.ai/v2/docs/cli), and
[shell API](https://opencode.ai/v2/docs/api), and
[foreground server authentication](https://opencode.ai/v2/docs/cli/web).
The recipe targets V2.0.22; component-level service/API behavior is tested, while
full baseline and workflow qualification remain incomplete.
