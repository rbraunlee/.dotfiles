> **Historical copy (2026-10-06)** of root `docs/implementation-plan.md`. W1–W9 launcher sequence; superseded as the active order by the separately approved one-slice plan on main. W1 accepted historically; W2 assembled, not real-qualified.
> Original root note remains ignored and untouched. Paths written as `docs/...` below refer to original drafting locations; use [the package history index](../README.md) for relocated files.

# Implementation plan — workflow first

**Updated:** 2026-10-06.
**Status:** W1 accepted by the user, including its documented nonblocking advisories.
W2 source/tests and disposable trusted fixtures authorized (2026-10-05); real W2
qualification requires separate approval after assembly. W3–W9 remain unauthorized.
**Current checkpoint:** W2 deterministic components are assembled. Independent
verification passed with the offline API-input gap recorded below; fresh read-only
review is in progress. No real qualification has run.
**Accepted scope:** implement the workflow with sandboxing disabled, using one
independent local clone per slice. Rethink and plan sandboxing as a separate
project after implementing the workflow.
**Contracts:** `docs/alignment.md`.
**Decision/change record:** `docs/brainstorming.md`.
**Terminology:** `docs/CONTEXT.md`.
**Regression findings:** `docs/loop-logic.md`.
**Historical plan/evidence:** `docs/archive/implementation-plan-sandbox-2026-10-04.md`
and the existing M2 checkpoint/qualification/proposal documents.

## 1. Scope and execution boundary

Deliver the planning-to-QA workflow first. Keep the previously agreed Coordinator,
one-slice Orchestrators, Builder, independent Tester/Reviewer and optional helpers.
Keep local specifications/tickets, deterministic claims/state, bounded execution,
verified integration, GitHub traceability and final human acceptance/merge.

Execution is **trusted local execution**, not a sandbox:

- One independent clone per slice, in its own directory and branch with its own
  Git metadata. No Git worktrees or shared-clone alternates.
- Each Orchestrator and its subagents/tools operate in that clone. Validate actual
  directory binding; a prompt naming a directory is not proof of tool locality.
- Repository setup/tests/builds may execute on the host under approved project
  commands. Use only explicitly trusted projects and approved development inputs.
- Clones do not prevent access to other files, credentials, networks or processes.
  Role tool permissions are workflow controls, not adversarial host containment.
- Only the launcher owns operational state and integration/PR operations through
  supported interfaces. Test normal permission restrictions and document bypass
  limits under the shared host identity; do not claim OS-level worker isolation.
- Keep secret references and redact reports. No production credentials/data,
  deployment or final agent merge into `main` is authorized. Ambient host access
  cannot be claimed absent; readiness must identify relevant exposure.
- Keep runtime, repair and concurrency bounds. Hard CPU/memory/PID/disk isolation,
  firewall/proxy policy and a credential broker are not workflow acceptance gates.

Application dependencies may use a project's existing approved Docker/Compose
services. That is project runtime setup, not sandboxing agent execution; no new
daemon/storage/firewall provisioning is implicit in this plan.

Do not delete sandbox source/evidence, undo host configuration, weaken existing
sandbox gates or add a flag that reroutes sandbox requests into host execution.
Implement the local path explicitly with truthful capability/status reporting.
Future sandbox design, extraction into another repository and a general backend
framework are outside this plan.

## 2. Reuse and proposed engineering approach

These are implementation proposals, not additional product decisions:

| Area | Approach |
|---|---|
| Existing M1 | Reuse accepted authorization, claims, leases, atomic ledger and status logic where compatible; retest changed interfaces |
| Launcher | Retain the narrow Linux-first Python host launcher; no general scheduling platform |
| Profile | A workflow-focused local profile: trusted commands, development service/access needs, limits, Git/PR conventions and QA controls; no mandatory sandbox fields |
| Planning inputs | Retain approved spec/tickets and immutable hashes/dependencies/criterion mappings; no operational writes into requirements |
| Runtime authority | One launcher-owned JSON ledger with OS-backed locks, atomic writes and durable checkpoints |
| Local runs | Launcher-owned run directories, independent clones, explicit baseline and session identity; preserve work on failures |
| Agent bundle | Snapshot locally owned prompts/skills per feature and record bundle identity; no worker image required |
| OpenCode connection | Qualify actual V2 session/agent/tool APIs and directory binding before selecting mechanics; no guessed endpoints or container-service assumptions |
| Integration | Disposable independent local candidate checkout; retain candidate refs; publish only an exact verified commit with an expected-head check |
| GitHub | Launcher-owned idempotent PR operations; workers do not receive PR credentials through the workflow; shared-host exposure remains a documented limitation |

Do not blindly reuse sandbox profiles, provider manifests or lifecycle state as
local-run contracts. Keep historical records readable without treating them as
valid authorization for new local runs. Preserve unrelated/uncommitted changes.

### Code-reviewed reuse map

Paths below are relative to `linux/opencode-routine/`; `routine/` denotes
`.local/lib/opencode-routine/routine/`.

| Existing code | Reuse and adaptation boundary |
|---|---|
| `routine/store.py` | Reuse stable `flock` files, private-path validation and fsync/atomic ledger replacement. Preserve historical records and unrelated ledger sections; same-user processes are not excluded by private file modes. |
| `routine/contracts.py` | Reuse strict JSON parsing, identifiers, hashes, normalized paths, criterion markers and graph validation. Add separate local validators; do not relax sandbox profile versions 1–3. |
| `routine/launcher.py` | Adapt immutable authorization, process-scoped Coordinator leases, exclusive claims and derived status. Retest request identities, execution-kind separation and baseline selection. |
| `routine/cli.py` | Reuse trusted administration versus typed Coordinator operations and JSON-lines responses. Add explicit local operations, never a sandbox-disable/fallback flag. |
| `routine/transfer.py` | Reuse configuration-blind, bounded Git bundle export from ordinary independent checkouts. Local clone creation and complete contribution-range admission are additional work. |
| `routine/inputs.py` | Reuse descriptor-based, bounded, hash-checked input copying where useful. Container mount targets and mount policy are not local contracts. |
| `routine/process.py` | Reuse bounded subprocess/deadline handling for launcher Git operations. Its sanitized environment and discarded stderr are not an unchanged project-command or shared-service authentication adapter. |
| `routine/sandbox.py`, `routine/checkpoints.py` | Reuse lifecycle patterns: validate ownership, journal intent before effects, retain failures and hold uncertain stopping. Do not reuse container identities, sandbox states or inspection records as local proof. |
| `.local/share/opencode-routine/worker/worker.py` | Reference command quoting, deadlines, late-success rejection and allowlisted evidence. Preserve its container-only entry point; fixed paths, private-server startup and service termination cannot be adopted for the shared local service. |
| `tests/test_m1.py`, selected `tests/test_m2*.py` cases | Retain historical tests; add local counterparts for contention, atomic-write crashes, malicious Git configuration, deadlines, duplicate launch and secret canaries. No live sandbox opt-in is implied. |

The existing `bundle-id` fingerprints worker-image assets, not the accepted local
agent/skill bundle. Keep it unchanged and introduce a distinct local bundle identity.
M1 validates declared baseline syntax and hashes; it does not establish that the
Git baseline exists, that the feature ref matches, or that actual local agent/skill
contents match the declared hash. Local authorization must close those gaps.

The current agent prompts still contain legacy state/phase behavior. In particular,
Orchestrator owns `current-slice.toml`, advances across slices and invokes mandatory
Refactorer/Cleaner phases. These prompts are adaptation inputs, not a usable local
execution bundle. Preserve existing agent edits and the untracked launcher package;
neither is disposable scaffolding.

### Refinement history — 2026-10-05

This in-place refinement follows the workflow-first draft and the accepted W2
basic-stopping and effective-configuration amendments recorded in
`docs/brainstorming.md`. It adds code-specific reuse boundaries, explicit local
schema proposals, W1/W2 work units and validation exits. It does not reopen
`docs/alignment.md`, accept qualification, authorize runtime work or supersede the
archived sandbox evidence. Later milestones retain their existing contracts and
remain outcome/acceptance-level plans.

The subsequent parallel-development refinement records independent workstreams
within a milestone, shared-interface/file ownership and sequential acceptance.
It does not enable the workflow's parallel worker dispatcher before W8.

## 3. Implementation sequence

Use **W1–W9** to avoid redefining historical M1–M11 or confusing M2 qualification
with workflow acceptance. Milestones are implemented and accepted sequentially;
independent components within the active milestone may be developed in parallel
under the ownership and authorization rules below.
Start with one real slice, then sequential dependencies, then parallel workers.

**Build order is not runtime scheduling.** The milestone sequence establishes the
workflow progressively; it does not remove the Coordinator or require finished
features to execute sequentially. In the completed workflow, the Coordinator selects
authorized dependency-ready slices and uses the launcher to dispatch up to the
configured concurrency into independent clones. Slice Orchestrators run their
Builder/Tester/Reviewer loops; the Coordinator tracks results and PR lifecycle and
coordinates gated, serialized integration. Successful integration can unlock
consumers. Further dispatch follows the authorized launch mode: default batches do
not refill, while explicit whole-feature mode can continue with newly ready work.

W1–W5 use explicitly approved, trusted disposable fixtures with known setup and
baseline checks. Approve fixture mutations before running them. They do not authorize
ordinary project execution before W6 onboarding/readiness or bypass setup approval.

Retain the accepted initial skill scope: `grill-with-docs`, `to-spec`, `to-tickets`,
`tdd`, `code-review`, `handoff`, `research`, `writing-for-agents`, `implement-spec`
and necessary setup/transitive dependencies. Use locally owned/adapted copies with
origin notes, not upstream runtime dependencies. W2/W3 validate role prompts and
execution/review/handoff/helper skills; W6 validates setup and upstream planning
skills; W7 validates adapted Coordinator scheduling. Loading skills never expands
role authority. Do not bulk-install unrelated skills or reimplement planning here.

```text
W1 Claims → W2 Local run → W3 Verified slice → W4 Verified integration
    → Gate A → W5 Recovery → W6 Project setup/PRs
    → W7 Sequential delivery/corrections → Gate B
    → W8 Parallel delivery → W9 Full-feature QA handoff
```

### Parallel development within a milestone

Parallel development of launcher components is distinct from parallel feature
execution by the finished workflow. W1 acceptance still precedes W2 execution,
W2's real gates precede W3, and Gate B precedes W8 parallel dispatch. Completing
an independent component is not milestone acceptance or permission to bypass a
runtime prerequisite. Delegation and fixture mutations require explicit execution
authorization; this section does not launch agents or approve runtime exercises.

Before fan-out, one implementation owner resolves the active milestone's shared
engineering interfaces from this plan and records them in its existing milestone
section. Do not create another plan or reopen accepted product contracts. Give each
shared interface/file one owner; consumers wait for its established contract. Use
at most three concurrent delegated workstreams initially, with disjoint file scopes;
this is a development limit, not a change to the workflow's automatic capacity pools.

| Active milestone | Establish before fan-out | Independent workstreams |
|---|---|---|
| W1 | Local schema/version rules; bundle inventory/snapshot interface; dispatch/claim records; baseline ownership; error/result shapes | Local validation in `local_contracts.py`; local bundle snapshot/fingerprint helpers; Builder-owned W1 tests/fixtures in separately assigned files. |
| W2 | Local adapter signatures; lifecycle states/checkpoints; session/command ownership; stop-request protocol; evidence schema | Clone/handoff preparation in `local_run.py`; V2 location/configuration/session/command adapter in `opencode_local.py`; Builder-owned contract tests and real qualification fixture preparation. |
| W6 | Approved profile/readiness and verified-publication inputs | Project-onboarding skill/profile work and GitHub traceability work. Detailed subdivision waits until W6 is active. |

For W1, the implementation owner retains `launcher.py`/`cli.py` adaptation,
authorization/baseline/ledger integration and final assembly. For W2, that owner
retains shared entry-point changes and assembly of preparation with the runtime
adapter. Other streams do not independently rewrite those files, mutate production
state or change sandbox gates. Shared test helpers also have one owner; establish
them first or use separate fixtures rather than concurrent edits to the same helper.

Test authoring belongs to Builder workstreams; independent Tester verifies without
editing product code or committed tests, and Reviewer remains read-only. Contract
tests may be developed against established interfaces while implementation proceeds,
but a mocked pass is not real runtime qualification. The implementation owner
reconciles contributions, runs combined regressions and obtains independent review
before presenting milestone evidence for user acceptance.

W2's two-clone routing/stopping qualification remains a separately approved joined
exercise after the relevant components are assembled. Parallel fixture preparation
does not authorize parallel runtime commands, OpenCode launches or production
dispatch. Keep W3–W9 outcome-level plans; add finer workstreams only when their
milestone becomes active and its prerequisites/interfaces are known.

### W1 — Approved planning package → exclusive local-run claim

**Starting point:** historical M1 was implemented and accepted. This milestone is
a compatibility/adaptation check, not a restart or automatic acceptance of changes.

**Deliver:** authorize approved immutable inputs and claim a slice for local mode.

#### W1 engineering clarification — authorized implementation, 2026-10-05

The current user instruction authorizes W1 source/test work and disposable fixtures
under `/tmp/opencode`, not W2, runtime launches, installation, production state,
GitHub writes or commits. W1 remains pending human acceptance.

Shared interfaces established before development fan-out:

- `local_contracts.validate_profile(profile)` and `load_package(root, feature_id)`
  enforce only local profile v4/approval v2, returning the existing
  `{manifest, profile, snapshots}` shape. Historical validators are unchanged.
- `local_contracts.validate_fixture_evidence(value, package)` accepts exact fields
  `version: 1`, `execution: "trusted-local"`, `baseline`, `profile_sha256`,
  `mutations_approved: true`, and `checks`. Checks exactly cover profile check names;
  each has `outcome: "passed"` and an identifier `evidence_ref`, or
  `outcome: "exception"` with identifier `evidence_ref`, `failure_ref`, `scope_ref`
  and `approval_ref`. References are approved non-secret evidence identifiers, not
  claims that W1 executed checks or independently established semantic exception scope.
- `local_bundle.describe_bundle(root, *, max_bytes, timeout)` returns
  `{sha256, inventory}`. Inventory is a sorted list of exact `{path, sha256}`
  entries; identity is SHA-256 of its canonical JSON. The dedicated, trusted bundle
  root contains agents, selected skills/resources and `provenance.md`; it is not
  an entire home/config directory. Explicit trusted source-file installation links
  may resolve to regular files; copied snapshots have no links.
- `local_bundle.snapshot_bundle(root, destination, expected_sha256, *, max_bytes,
  timeout)` exclusively creates a new directory, verifies every copied file and
  returns the same identity shape. `verify_snapshot(destination, expected_sha256,
  *, max_bytes, timeout)` rejects links, omissions, additions and changed bytes.
  Interrupted copies are retained and cannot be published as authorization.
- Trusted administration exposes `authorize_local(project_id, feature_id,
  project_root, bundle_root, api_path, configuration_path, fixture_evidence)`;
  reviewed API/configuration bytes must match profile hashes. It freezes the bundle
  outside the project before publishing a feature record. No runtime configuration
  is loaded or executed. The feature owns immutable package/evidence, explicit
  `schema_version: 1`, `execution`, bundle snapshot reference and operational
  `verified_head` (commit/branch), initially equal to the approved baseline.
- `authorize_local_dispatch(project_id, feature_id, slice_id, dispatch_id,
  authorization_id)` records a separate immutable, single-slice scope in that
  feature's `dispatches`. Its identity includes package authorization, selected
  baseline and execution kind. It does not authorize alternative slices.
- `Coordinator.claim_local(slice_id, run_id, authorization_id, dispatch_id,
  baseline)` creates an explicit local schema/execution record. Request identity
  includes dispatch ID/identity, selected baseline and the existing identities.
  Claims carry bundle snapshot, criteria, budgets, command limits and credential
  references, with no runtime/inactivity start. Reuse with changed inputs fails.
- Baseline inspection is owner-controlled, bounded and configuration-blind: read
  only an ordinary independent repository's objects and exact loose/packed feature
  ref, reject alternates/symlink metadata, and inspect commits through a fresh bare
  Git directory. No source config/hooks/replacements or project commands are used.
- Responses retain `{run, existing}` and authorization identity/`existing` shapes;
  errors retain `{error: {code, message}}` with safe fixed diagnostics. Status adds
  execution, verified head, dispatch scopes and derived hold/wait reasons. A moved
  ref or persisted Coordinator interruption is a hold, never a verified-head update.
  Sandbox operations explicitly reject local records before invoking adapters.
- Files have one owner: parent owns `launcher.py`, `cli.py`, baseline helper and
  ledger assembly; delegates own `local_contracts.py` plus its isolated tests,
  `local_bundle.py` plus its isolated tests, and `tests/test_w1.py` respectively.
  No delegate edits shared/historical files or commits. Independent verification
  and fresh read-only review follow combined assembly.

These reversible engineering choices do not change accepted workflow contracts;
effective configuration, real skill/role adaptation and readiness remain later gates.

Implementation observations: local status is an observational view of one ledger
revision, with bounded planning/snapshot/Git revalidation performed outside
`ledger.lock`; observed drift produces hold reasons without modifying the ledger
or adopting a ref. The baseline inspector's disposable bare Git metadata is not a
worker checkout. Snapshot files are copied read-only integrity aids; same-user
processes can chmod/replace them, so every claim revalidates their inventory.

**Early execution scope:** W1/W2 support only an explicitly selected,
dependency-ready slice of an approved trusted fixture. W1 creates no checkout,
runs no setup/check command and starts no OpenCode session. Batch/whole-feature
scheduling remains W7; production parallel dispatch remains W8.

#### W1.1 — Explicit local contracts and compatibility

Retain the current project-relative locations:

- `.opencode/routine/project.json` for the approved profile.
- `.opencode/routine/features/<feature-id>/approval.json` for the approval manifest.
- Existing referenced UTF-8 spec/ticket paths and criterion markers.
- `$XDG_STATE_HOME/opencode-routine/ledger.json` as the sole runtime authority.

Implement these strict, fixture-focused schema proposals:

| Contract | Local shape |
|---|---|
| Profile | Version **4**, with `execution: "trusted-local"`; exact fields `version`, `execution`, `commands`, `command_limits`, `budgets`, `concurrency`, `credential_refs`, `runtime`, `services`, `qa`. |
| Commands | Existing `setup` list and nonempty named `checks` map. Each entry has only `argv` and `timeout_seconds`; no Coordinator-supplied commands, environment values or shell fragments. |
| Command limits | Positive integer `command_seconds`, `input_bytes`, `output_bytes`; deadlines/byte limits bound preparation and evidence handling, not host filesystem or resource containment. |
| Budgets | Existing `slice_seconds`, `inactivity_seconds`, `integration_seconds`, `repairs`; initial defaults 3600/600/1800 seconds and two repairs, with explicit approved project values. |
| Concurrency | Positive integer `workers_per_feature`, initially three. Host worker and integration-check caps remain separately launcher-owned at three each; W1/W2 do not enable parallel scheduling. |
| Runtime | Exact `opencode_version`, `api_sha256`, `configuration_sha256`, `connection_ref`. Hashes identify reviewed API/configuration inputs; the connection reference names approved existing service/authentication context, never secret values. |
| Services/QA | W1/W2 require `services: []` and `qa: {"kind": "none", "start": null}`. W6 explicitly extends/version-controls ordinary project service, access and QA contracts without rewriting existing authorizations. |
| Approval | Version **2**, existing spec/ticket/hash/baseline fields plus `execution: "trusted-local"`; accepted only with the local profile. The bundle hash now identifies the local prompt/skill inventory, not worker-image assets. |

Use existing strict scalar/command/graph validation where compatible. Require
positive deadlines within command/slice limits and a shared repair budget of zero
through two. Credential references are approved development/test/model references
only; no values or production grants belong in these artifacts.

Keep version-1 manifests and profile versions 1–3 on their historical path. Reject
mixed local/sandbox packages and reject historical authorization/run identities on
local operations. Do not migrate, relabel or add local execution authority to old
records. Use a new approved feature identity for changed immutable packages, as the
existing implementation requires. A copied sandbox profile is not a local profile.

Criterion checks resolve the approved manifest against the full spec and ticket
mappings. They do not prove semantic completeness or implemented acceptance;
slice evidence and final full-spec review remain W3/W7 gates.

#### W1.2 — Freeze the authorized package and local bundle

- Retain exact-byte planning snapshots and authorization hashes; even formatting
  drift is a changed input, not a silently updated authorization.
- Trusted administration supplies the local bundle and reviewed API/configuration
  inputs. Coordinator operations cannot choose new filesystem roots or approve them.
- Define the bundle fingerprint as the digest of a canonical, sorted inventory of
  normalized relative paths and file-content hashes. Include agent definitions,
  selected skill files and necessary referenced resources, plus provenance notes.
  Resolve approved installation links to reviewed source files before copying;
  snapshots contain regular copied files, not links back to mutable installations.
- Freeze one bundle per feature when execution is authorized, outside the project
  under launcher-owned artifacts. Validate every copy against the approved inventory
  before publishing its ledger reference. An interrupted/incomplete copy is retained
  diagnostically and cannot establish authorization.
- Runs/recovery reference that feature snapshot. Later global/local edits cannot
  silently change it; effective runtime configuration still needs W2 validation.
- Fixture authorization includes approved mutations and existing green baseline
  check evidence, or a user-approved narrow exception. W1 records/validates that
  reference; it does not run commands or replace W6 project readiness.

#### W1.3 — Baseline, scope, claims and ledger updates

Distinguish the immutable **approved initial baseline** from the launcher-owned
**current verified feature head**, initially seeded from approved baseline evidence.
Validate commit existence and the expected feature ref through configuration-blind
Git inspection. Reuse the sanitized object-export pattern, not source-repository
hooks, includes, fsmonitor, helpers or replacement refs.

Claims record the exact selected verified commit and feature branch. W4 later
advances the operational head after verification; consumers then start from that
head without changing the approved initial-baseline manifest. A mismatched/moved
ref is held, not adopted as newly verified work.

- Preserve the per-feature Coordinator OS lease and token ownership checks.
- Record the early single-slice dispatch authorization separately from immutable
  planning approval in the same ledger. Trusted administration selects its slice;
  Coordinator cannot widen it. Subsequent launches can authorize further approved
  work without reapproving unchanged planning or replacing feature identity.
- Local request identity includes dispatch authorization, `execution`, selected
  baseline, and existing project/feature/slice/run/package/Coordinator identities.
  Identical requests return one durable claim; changed reuse fails.
- Under `ledger.lock`, validate current ownership/dispatch scope, reject input drift
  and unsatisfied dependencies, then write run and slice ownership atomically.
  Dependency satisfaction still requires verified integration, not fixture success.
- Keep hashing/Git/copy operations outside the short ledger critical section;
  revalidate ownership and input identity before publishing their results.
- Preserve unrelated ledger sections. Do not replace stable lock files. New local
  records carry explicit execution/schema identities; old records remain readable.
- Claiming does not start runtime/inactivity timers. Coordinator interruption keeps
  the existing deliberate-recovery hold; no implicit takeover or budget reset.
- Status is a derived ledger view with execution kind, selected baseline and
  waiting/hold reasons. It never rewrites requirements or claims alternate work.

**Implementation targets:** adapt `launcher.py`/`cli.py`, reuse `store.py` and
validation primitives, and add `routine/local_contracts.py` plus local bundle
snapshot helpers. Keep sandbox validators and entry points intact; do not introduce
a general backend abstraction or a second state store.

**Acceptance**

- Reject changed/unapproved inputs, invalid graphs/profiles, unsatisfied dependencies
  and unresolved required criteria.
- Identical requests reuse one claim; reused IDs with different inputs fail.
- One Coordinator per feature; exclusive slice ownership and atomic ledger updates.
- Specs/tickets remain unchanged; status views are derived from the ledger.
- Old sandbox records remain preserved and cannot be implicitly adopted as local runs.
- No eligible work returns an explanation, not alternative unauthorized work.

**Proof:** retain the historical regression suite and add `tests/test_w1.py` for
local schemas, claim contention, drift and interrupted writes. Include:

- Mixed local/sandbox package and cross-use authorization/run rejection.
- Historical feature/run/inspection/environment records unchanged by local work.
- Missing commit, missing/moved feature ref and malicious hook/config canaries.
- Bundle-content drift, incomplete snapshots and unchanged per-feature snapshots.
- Reused request IDs with changed baseline, execution kind or dispatch scope.
- Attempted scope expansion and a blocked selected slice without alternative claims.
- Kernel lease release with persisted recovery hold; no timer started by a claim.
- Old-or-new complete ledger updates around each existing atomic-write checkpoint.

**Exit:** fresh local authorization/claim tests pass with preserved historical
behavior. Record reused M1 evidence separately from adaptation results. W1 acceptance
does not authorize session launches or claim sandbox/local-runtime qualification.

#### W1 implementation evidence — 2026-10-05 (pending acceptance)

- Adapted only `routine/launcher.py` and `routine/cli.py`; added
  `routine/local_contracts.py`, `routine/local_bundle.py`,
  `routine/local_baseline.py`, and `tests/test_w1.py`,
  `tests/test_w1_contracts.py`, `tests/test_w1_bundle.py`,
  `tests/test_w1_baseline.py`, `tests/test_w1_cli_errors.py`. Paths are relative to
  the existing launcher package.
  This plan is updated in place. Existing agent edits, sandbox source/tests and
  retained evidence are not removed, migrated or overwritten. No commits made.
- TDD red checks established absent local interfaces before their implementation.
  Additional red regressions exposed ancestor-directory timestamp false positives
  during sibling activity and a feature ref moving during commit inspection.
  Ancestor inode/type checks now permit unrelated activity while bundle-subtree
  content checks remain strict; baseline inspection now rechecks the feature ref
  after inspecting the commit. Deliberate snapshot-tamper fixtures chmod copied
  read-only files, preserving rejection assertions rather than claiming containment.
- Initial assembled owner checks: **108 W1 tests passed** (37 assembled
  authorization/claim/CLI, 24 local contracts, 41 bundle, six baseline tests).
  After review repairs: **114 W1 tests pass**, including nine baseline tests
  (SHA-256 Git objects, tag rejection and loose/packed object symlink rejection)
  and three diagnostic tests (including real malformed request/planning/evidence).
  Historical M1 alone: **25 passed**. Complete historical daemon-free regressions:
  **346 collected, 328 passed, 18 live tests skipped**. The M1 result is regression
  evidence, not automatic acceptance of the new local interfaces.
- Commands run: `python3 -B -m unittest discover -s linux/opencode-routine/tests
  -p test_m1.py -v`; equivalent discovery with `-p 'test_w1*.py'` and
  `-p 'test_m*.py'`; final full discovery without `-p` collected **460 tests,
  442 passed, 18 skipped**. Live image opt-ins `OPENCODE_ROUTINE_TEST_IMAGE`,
  `OPENCODE_ROUTINE_COMPONENT_IMAGE`, `OPENCODE_ROUTINE_STORAGE_IMAGE` were removed
  explicitly for combined/regression runs. W1 fixtures, Git commits, temporary homes
  and state were disposable under `/tmp/opencode`; no workflow workers, OpenCode
  runtime sessions, project setup/check execution through the launcher, live
  sandbox qualification, GitHub writes, host install or production mutation occurred.
- Initial fresh read-only review found three reproducible W1 blockers: annotated
  tag OIDs were peeled as commits, nested object-storage symlinks passed inspection,
  and duplicate JSON keys could leak through exception diagnostics. Dedicated
  regressions failed before repairs. The inspector now requires the exact OID's
  object type to be `commit` and descriptor-scans object metadata with byte/depth/
  deadline bounds; the CLI exports fixed allowlisted diagnostics without raw input
  keys or exception details. Historical error codes and sandbox gates remain intact.
  No accepted contract was changed. Fresh post-repair read-only review found **no
  remaining W1 blockers** and independently passed **114 W1** and **25 M1** tests;
  additional disposable probes rejected nested FIFO object storage, excessive
  metadata and excessive depth. The advisory below remains nonblocking for W1's
  explicitly trusted selected fixtures.
- Final independent verification: **460 collected, 442 passed, 18 live skipped**,
  including **114 W1 passed** and **328 historical passed**. All ten final Python
  source/test hashes were identical before and after verification and matched the
  fresh review. Final command added `TMPDIR=/tmp/opencode` and
  `PYTHONDONTWRITEBYTECODE=1` to the explicit no-live-opt-in environment above.
  Initial historical runs used the existing N1 tests' system-default temporary
  directory; final validation redirects that default under `/tmp/opencode` too.
  No production state or host infrastructure was changed.
- Independent evidence retained at
  `/tmp/opencode/w1-independent-verification-3tmqbixh/report.md`,
  `hashes-final.json` and `full-unittest-frozen.log` in that same directory. Earlier
  intermediate passes are superseded, not final acceptance evidence. Reviewed/tested
  code/test set identity: SHA-256 of canonical JSON of the sorted list of
  `{path, sha256}` for the five source and five test files listed above, with paths
  relative to `linux/opencode-routine/`:
  `3967eb57714b43c126321125e4a57f69873f93c28869cd7d04d9a284a5da940f`.
  The plan is excluded from that code/test fingerprint. All ten files parse as
  Python and have no trailing whitespace; tracked `git diff --check` also passed.
- Remaining scope boundaries: W1 validates approved evidence references and bytes,
  not semantic exception scope, development credential provenance, actual API or
  effective runtime configuration. Real clone/session routing, permission probes,
  stopping and configuration qualification remain W2; role/skill adaptation and
  implementation/evidence gates remain W3. No runtime qualification is claimed.
  Filesystem deadlines are cooperative around local filesystem calls, and private
  modes/independent metadata are not same-user security containment. Interrupted
  snapshot destinations remain diagnostic and are not silently adopted on retry.
  Initial review advisory: bundle content-byte/deadline/nesting bounds are not a
  separate entry/inventory/descriptor cap; very large tiny-file inventories may
  consume excessive metadata/descriptors before their content-byte limit. W1 uses
  explicitly trusted selected fixture bundles; no hard metadata/resource quota is
  claimed. This remains visible for acceptance rather than being reported as passed.
  Independent verification also notes nonblocking test gaps for dedicated baseline
  deadline/output-exhaustion and packed-ref race cases; metadata/depth rejection
  received separate fresh-review probes, not committed dedicated test coverage.
- **Acceptance boundary:** no unresolved blocking implementation/review findings
  or required contract changes identified. W1 is presented for the user's decision,
  not marked accepted. Stop here; W2 and all workflow runtime launches remain
  unauthorized.

#### W1 review findings and disposition

This is the consolidated findings record for the implementation above, not a new
plan or acceptance decision. Source paths below are relative to
`linux/opencode-routine/.local/lib/opencode-routine/routine/`; test paths are
relative to `linux/opencode-routine/tests/`.

| Finding | Disposition | Repair / evidence |
|---|---|---|
| Annotated tag OIDs could be accepted as exact commit anchors because Git peeled the tag. | Blocking; **fixed and independently re-reviewed**. | `local_baseline.py` checks `cat-file -t` on the exact OID and requires `commit`. `test_w1_baseline.py` rejects annotated tags. |
| Nested symlinks in loose or packed object storage could bypass independent-metadata validation. | Blocking; **fixed and independently re-reviewed**. | `local_baseline.py` descriptor-scans object storage before and after commit inspection, rejecting links/special files within metadata, depth and deadline bounds. Tests reject linked object-prefix directories, loose objects, pack directories and pack files. |
| Duplicate JSON keys could be echoed into exported diagnostics, leaking input-derived text. | Blocking; **fixed and independently re-reviewed**. | `cli.py` emits fixed allowlisted messages while preserving error codes. `test_w1_cli_errors.py` exercises actual malformed Coordinator requests, planning approvals and fixture evidence with secret canaries. |
| A feature ref moving during commit inspection could return success. | Assembly defect; **fixed**. | The baseline inspector rechecks the feature ref after inspecting the commit. Its dedicated regression passes; fresh review also confirmed the moved-ref reproduction is rejected. |
| Unrelated sibling activity changed ancestor timestamps and caused false bundle-drift failures. | Assembly defect; **fixed**. | `local_bundle.py` validates ancestor inode/type identity while retaining strict bundle-subtree change checks. Sibling-activity and concurrent duplicate-claim regressions pass. |
| Snapshot-tamper fixtures initially assumed copied files were writable. | Test-fixture defect; **fixed without weakening assertions**. | Deliberate same-user tampering explicitly chmods read-only copies; modified, missing and linked snapshot inputs remain rejected. |
| Bundle traversal captures the complete inventory and retains directory descriptors before enforcing content-byte limits. | **Open advisory; nonblocking for trusted W1 fixture bundles**. | No separate entry/inventory/descriptor cap exists. Consider explicit metadata caps before broader use; do not describe content-byte/deadline bounds as hard resource containment. |
| Dedicated baseline deadline/output-exhaustion and packed-ref race regression cases are absent. | **Open, nonblocking coverage gaps**. | Metadata/depth failure paths received disposable fresh-review probes, but those probes are not committed dedicated coverage. Additional boundary tests remain useful. |

**Final disposition:** independent full verification passed **442 tests**, with
**18 live tests skipped**; all **114 W1 tests** passed. Fresh final read-only review
identified **no remaining W1 blockers** and matched the verified source/test hashes.
Evidence paths and the content fingerprint are recorded immediately above.

**Next decision:** the user accepts W1 or requests further W1 work. Acceptance has
not been recorded. After acceptance, W2 implementation requires explicit
authorization; its joined real OpenCode routing/configuration/stopping exercise
requires separate approval after assembly. No further implementation or runtime
work is authorized by this findings record.

**W2 readiness recommendation:** the recorded W1 findings do not block moving to
W2's trusted-fixture implementation after the user's W1 acceptance and explicit
W2 authorization. The remaining metadata-cap advisory and dedicated-test gaps
are visible limitations, not failed W1 gates; they do not establish runtime
qualification or authorize broader project use.

W2 does not need a competing plan or another product-contract alignment round.
Its existing scope, work units, acceptance criteria and qualification boundary
are sufficient. At its start, resolve the bounded engineering details required by
the parallel-development section **in this existing plan**: concrete local adapter
signatures, lifecycle/checkpoint record shapes, session/command ownership,
stop-request handling and evidence schema. Match the adapter to the reviewed
installed V2 release/API rather than guessing mechanics. Establish shared file
ownership before any development fan-out. The joined real routing, configuration
and owned-stopping qualification remains separately approved; uncertain results
hold W3 rather than silently weakening a gate. Escalate if that work reveals a
required change to an accepted contract.

### W2 — Claimed slice → prepared clone and directory-bound local session

**Deliver:** prepare an independent clone from the exact authorized feature commit,
provide the approved planning/bundle snapshot and run a bounded fixture command.

#### W2 engineering interfaces — established before fan-out, 2026-10-05

The user accepted W1 and authorized W2 implementation, deterministic injected-adapter
tests and disposable fixtures under `/tmp/opencode`, including fixture Git commits.
No real workflow/session/command launch, live sandbox test, host installation,
infrastructure/production mutation, GitHub write or repository commit is authorized.
W1's ten-file identity was rechecked before editing and exactly matched
`3967eb57714b43c126321125e4a57f69873f93c28869cd7d04d9a284a5da940f`.
Historical W1 acceptance-boundary prose above records the earlier session, not a
withdrawal of this subsequent user acceptance. Its advisories remain visible.

Concrete shared interfaces (Python; keyword-only bounds; fixed safe RoutineError
diagnostics; consumers do not redefine these contracts):

- `local_run.prepare_clone(feature, run, destination, *, timeout, max_bytes,
  checkpoint)` exclusively creates the owner-derived artifact root. `checkpoint(name,
  details)` journals intent/observed identity before/after effects and checks stopping;
  the helper never writes the ledger. Returns exact keys `artifact`, `checkout`,
  `branch`, `commit`, `git_dir`, `bundle_sha256`, `handoff`. Handoff has `path`,
  `sha256`, `inventory` (sorted `{path, sha256}`); includes all exact planning
  snapshots, approval/profile, explicit criteria/run context and full frozen bundle.
  `verify_prepared(prepared, run, *, timeout, max_bytes)` rechecks identities without
  adopting changes. Branch is `routine/<feature-id>/<slice-id>/<run-id>`.
- Runtime adapter methods: `qualify(*, directory, handoff, runtime, bundle_sha256,
  deadline, max_bytes)`; `create_session(*, directory, run_key, driver_id, deadline)`;
  `discover_children(*, session, directory, run_key, deadline, max_bytes)`;
  `start_command(*, directory, session, argv, timeout_seconds, run_key, driver_id,
  deadline)`; `poll_command(*, command, deadline, max_bytes)`;
  `collect(*, sessions, commands, deadline, max_bytes)`;
  `stop(*, directory, sessions, commands, run_key, driver_id, deadline, max_bytes)`.
  Deadlines are absolute monotonic values within one driver; durable runtime start/
  deadline are epoch seconds and are never reset. Every call is checked for late
  return. No implicit transport/service discovery or service start is permitted.
- Qualification result exact fields: `version`, `api_sha256`,
  `configuration_sha256`, `bundle_sha256`, `directory`, `qualification`
  (`deterministic` or `real`), `roles_sha256`, `discovery_sha256`,
  `permissions_verified`, `stopping_verified`, `delegation_verified`. All three
  observations must be true to exercise commands. Injected observations are
  contract tests, never real qualification. Offline approved discovery must precede
  any config/location loading; missing visibility holds rather than executes.
- Session records exact fields `id`, `directory`, `parent_id`, `owner` (run key).
  Child records must form an owned parent chain and share the canonical directory.
  Command records exact fields `id`, `directory`, `session_id`, `owner`, `processes`
  (list of exact `{pid, start_id}` process identities). Poll returns exact
  `status` (`running`, `exited`, `timeout`, `killed`), `exit` (integer or null),
  `progress` (boolean). Heartbeats are not progress; only live unexpired commands
  suppress inactivity. Real descendant observability is a qualification prerequisite.
- Collection returns only `diagnostics`: bounded exact `{code, count}` records,
  with codes `command_failed`, `command_timeout`, `stop_uncertain`, `output_omitted`.
  Raw output/config/auth/exception strings are not copied. Stop returns exact
  `confirmed`, `sessions` (IDs), `commands` (IDs), `descendants_stopped`,
  `unrelated_preserved`; exact registered sets and true observations are required.
  Collect/save diagnostics durably **before** any destructive shell-remove request.
  Interrupt/client cancellation/API record deletion alone cannot confirm stopping.
- Parent-owned `local_lifecycle.py` integrates Store/Coordinator with these helpers;
  `LocalLifecycle(adapter=None, *, clock=time.time, monotonic=time.monotonic,
  sleep=time.sleep, checkpoint=None).prepare(coordinator, run_id)` and
  `.fixture_check(coordinator, run_id)` return existing `{run, existing}` shapes.
  Launcher accepts optional injected `local_adapter`; absent approved runtime
  assembly is fail-closed. `Launcher.local_stop(project_id, feature_id, run_id)` is
  a trusted stopping-only operation, also exposed on Coordinator, not a new lease.
- Run ledger adds `local` version 1 with `driver` (`id`, `coordinator_token`, `pid`),
  `artifact`, `runtime_started_at`, `runtime_deadline`, `last_progress_at`,
  `checkpoints` (ordered `{sequence, effect, phase, at, identity}`), `prepared`,
  `configuration`, `sessions`, `commands`, `checks`, `diagnostics`, `stop_request`.
  `sessions` contains the exact adapter ownership records; each `commands` item is
  `{identity, name, argv_sha256, deadline, status}`, where `identity` is the exact
  adapter command record. Each check is `{name, argv_sha256, exit, deadline,
  outcome}` (`passed` or `failed`); setup entries use generated `setup-<index>` names.
  Effect phases are `intent` and `observed`. Creation intent is saved before call;
  returned ownership before use. Interrupted active states become `local-held`,
  never resume. One stable nonblocking lifecycle lock/driver per run, short ledger
  transactions, driver fencing and ownership revalidation precede publication.
  Runtime/repairs survive repeated operations; fixture pass does not integrate.
  A narrow reservation check rejects unavailable host (three) or feature driver
  capacity before starting budgets; held uncertain drivers retain reservations.
  This is not W8 scheduling/queue dispatch. Command deadline begins at creation
  intent, not at returned ID. Stopping/diagnostic observation has one combined
  command-seconds allowance after execution expiry; it cannot launch new work or
  reset/extend the consumed slice runtime. Holds carry a fixed allowlisted
  `hold_reason`; status derives missing-driver/unconfirmed-stop observations.
- Stop request exact `{id, requested_at}` is atomically persisted using only
  `ledger.lock`, never lifecycle lock. Owning driver observes during bounded calls/
  polling and checkpoints. No driver/stale driver/unprovable stop becomes held,
  without unowned termination or automatic takeover. Held repeats return held.
  Results have `execution`, `outcome`, `qualification`, `evidence_sha256`;
  outcome is fixture-passed/failed/held, not ready-for-integration. Evidence is
  allowlisted identities/check exits/deadlines/diagnostic counters only.

File ownership: parent exclusively owns this plan, `launcher.py`, `cli.py`,
`local_lifecycle.py` and `tests/test_w2_assembly.py`; clone Builder exclusively owns
`local_run.py` and `tests/test_w2_clone.py`; V2 Builder exclusively owns
`opencode_local.py` and `tests/test_w2_adapter.py`; test/fixture Builder exclusively
owns `tests/test_w2.py` and `tests/w2_fixture.py` (sole shared fixture-helper owner).
W1/historical tests/helpers, sandbox source/evidence and agent edits are read-only.
Delegates use established interfaces and separate fixtures, not shared-file edits.
Independent Tester and fresh Reviewer follow assembly without source/test edits.

Release evidence: package-manager metadata identifies installed OpenCode **2.0.22-1**
(no OpenCode command executed). Authoritative tagged contract is
`https://raw.githubusercontent.com/anomalyco/opencode/v2.0.22/services/www/public/openapi.json`;
V2 API/configuration guides were read. The current published OpenAPI differs from
the tagged release and must not substitute for it. Runtime API byte identity and
actual configuration/routing/delegation/stopping still require the separately
approved exercise. Missing effective/descendant visibility must hold, not guess.

#### W2.1 — Local preparation and durable ownership

Add `routine/local_run.py` for local preparation/checkpoint orchestration and
`routine/opencode_local.py` for a release-specific service/session/command adapter.
Use dependency injection for contract tests, not a runtime backend framework.

Derive paths exclusively from validated run identities:

```text
$XDG_STATE_HOME/opencode-routine/artifacts/local-<run-key-hash>/
  handoff/
  checkout/
  evidence/
```

Coordinator requests identify an already claimed run; they cannot supply checkout
paths, commands, service URLs, configuration fragments or authentication values.
Expose explicit typed `local-prepare`, `local-fixture-check` and `local-stop`
operations, alongside status. Sandbox operations never route to these controllers.

Preparation algorithm:

1. Acquire a stable per-run lock, then briefly `ledger.lock`. Validate execution
   kind, claim, dispatch authorization, active Coordinator token and current inputs.
2. Persist preparation intent, artifact identity and the runtime-budget start before
   creating files or sessions. No capacity-wait time is charged. Never reset an
   existing start/deadline on repeat calls.
3. Exclusively create the derived artifact directory. Existing directories,
   symlinks or collisions hold the run; do not overwrite/adopt/remove them.
4. Export the exact claimed commit with `transfer.export_bundle`, using approved
   command/byte limits. Record the bundle hash; partial export is retained, not used.
5. Clone the bundle with a fresh empty Git template and sanitized launcher Git
   configuration. Create `routine/<feature-id>/<slice-id>/<run-id>` and verify HEAD,
   distinct checkout, real independent `.git`, no alternates and no worktree link.
6. Materialize full spec, ticket, explicit applicable criteria, profile and frozen
   feature bundle in `handoff/`, with exact hashes and documented readable paths.
   These need not be committed to application code. Never provide only summaries
   or host paths inaccessible to the role sessions.
7. Revalidate ownership and save clone/handoff identities before proceeding to the
   effective-configuration gate and session creation. All ledger writes remain
   launcher-owned; handoff/evidence files are inputs/results, not status authorities.

Use short ledger critical sections; external calls run under the per-run lifecycle
lock held by one lifecycle driver. `local-stop` records a stop request under
`ledger.lock` without waiting for that lifecycle lock; the owning driver observes
it during bounded polling and stops its registered work. A missing/unresponsive
driver produces a hold, not another driver or unowned stopping. W5 owns deliberate
crash recovery. Record a driver identity so stale drivers cannot publish new state.
Checkpoints journal effect intent and observed identities in the ledger. Bound the
combined Git bundle, planning and copied bundle inputs by approved preparation-byte
limits; byte limits must not be misreported as a quota on the local checkout.
Interrupted/in-progress preparation is held for deliberate W5 recovery, not resumed
or relaunched automatically. Snapshot modes are integrity aids, not same-user
filesystem containment.

#### W2.2 — Qualify actual V2 location and configuration behavior

Use only the approved existing service connection/authentication context. Do not
start/restart/terminate the shared service or inherit a container-specific server
password/startup mechanism.

Qualification sources are the [V2 API reference](https://opencode.ai/v2/docs/api/),
the [published OpenAPI contract](https://opencode.ai/v2/openapi.json) and the
[V2 configuration guide](https://opencode.ai/v2/docs/config/). The published
contract documents session creation with `location.directory`, location-bearing
session records, linked children starting at their parent's location, and
location-scoped configuration/shell operations. This establishes candidate mechanics,
not qualification on the installed release. Before relying on them, match the
actual release/API contract to the reviewed inputs and test real behavior.

- Bind the parent session explicitly to the canonical slice directory. Register
  parent/child session IDs and relationships; use session location, not project ID,
  prompt text or shell `cwd` alone, as routing identity. Independent clones can share
  a project ID/canonical project association.
- Persist session-creation intent and run metadata before the request; persist its
  returned ID/location before sending a prompt. An ambiguous response is held; never
  issue another create merely because the first reply was lost.
- Inspect approved discovery inputs before loading executable configuration. Account
  for global configuration, every relevant ancestor through filesystem root,
  project/clone configuration, file-based definitions and applicable session overrides.
- Reconcile discovered sources and resolved agents against approved configuration
  inputs and the frozen bundle. Include role permissions, plugins, MCP servers,
  skills and executable configuration such as formatter/LSP commands.
- Record non-secret identities only. A configuration response may describe ordered
  documents/sources rather than prove resolved tool behavior: compare resolved roles
  and run actual permitted/denied tool probes as well. Missing observability or
  unapproved overrides hold the run before fixture execution/W3.
- Do not execute an unapproved plugin/MCP/configuration command merely to inspect it.
  If the approved effective configuration cannot be established on the shared service,
  report the blocker and proposed qualification/setup work; do not silently launch a
  private service, mutate global configuration or weaken the gate.
- Use minimal adapted fixture role contracts for routing/permission probes. W3
  validates the real implementation/testing/review loop; do not run legacy prompts
  that create shared TOML state, advance to another slice or delete planning inputs.

#### W2.3 — Bounded commands, stopping and evidence

- Run only fixture-approved setup/check commands through the qualified local adapter,
  with explicit request location and checkout `cwd`. Quote argv if the installed
  API requires a command string; never concatenate unvalidated shell fragments.
- Bound every API call and command by its own deadline and remaining slice runtime.
  Capture actual exits; late-observed success is timeout, not a pass.
- Track command identity, ownership, deadline and progress. Quiet live tracked
  commands suppress inactivity only until their deadline; dead/expired commands do
  not. Heartbeats alone are not progress. Total slice time still includes setup.
- Register owned parent/child sessions, tracked commands and observable process
  identities before further work. Qualify discovery/registration of genuinely
  delegated subagents, not only manually created child sessions.
- On normal fixture completion, failure, timeout or explicit local-stop, collect
  evidence and stop only owned execution. Confirm parent, child and command/descendant
  termination. An interrupt acknowledgement or cancelled HTTP client is not proof
  of stopped work; uncertain ownership/stopping produces a hold.
- Shared service and unrelated sessions/processes must survive. Never substitute
  service shutdown, broad process-name matching or unowned process termination.
- Preserve bounded required diagnostics before destructive command-record removal.
  The published shell-remove operation also removes retained output; qualify this
  behavior and do not lose evidence by cancelling/removing first.
- Export allowlisted run/clone/session/runtime/configuration identities, argument
  identities, check exits/deadlines, qualification observations and approved redacted
  diagnostics. Exclude secret values, auth headers, raw effective configuration and
  raw command output; regex replacement alone is not redaction proof. Retain only
  approved bounded non-secret diagnostics, not arbitrary secret-bearing logs.

Local preparation states are `local-preparing`, `local-prepared`,
`local-starting`, `local-running`, and `local-stopping`, followed by
`local-fixture-passed`, `local-failed` or `local-held`. Persist effect checkpoints
before session/command creation and returned identities before use. A held or
interrupted record is never successful and blocks relaunch pending recovery.
Identical completed requests return their existing result without new effects;
held results remain visibly held.

`local-fixture-passed` means only the approved W2 fixture path passed and owned work
was confirmed stopped. It is neither `ready-for-integration` nor slice integration;
consumers remain blocked. Retain successful clones until acceptance and failed/held
clones until explicit cleanup. W5 extends stopping into comprehensive crash recovery
and supervision; W2 must establish basic stopping before W3 is enabled.

**Acceptance**

- Independent Git metadata, distinct branch and directory, no alternates/shared `.git`.
- Existing destination/collision is held, not overwritten or silently adopted.
- Fixture setup/mutations have explicit approval and known baseline checks; no
  ordinary project onboarding is skipped to reach this early milestone.
- Parent and real subagent tools use the intended slice directory; parallel fixtures
  cannot accidentally write in another slice or the user's original checkout.
- Verify the effective role/tool configuration against approved inputs, including
  relevant inherited global, ancestor and project configuration. Record its
  non-secret identity; a copied prompt/skill bundle alone is insufficient proof.
  Unapproved overrides or unverifiable effective configuration hold the run before
  W3; do not silently accept changed permissions or role behavior.
- Record run/clone/baseline/session identities before and around external effects;
  an interrupted launch is held for explicit recovery, not duplicated.
- Local setup/check commands are approved, deadline-bound and report actual exits.
- Before enabling the W3 implementation loop, prove basic stopping of the run's
  owned parent/subagent sessions and tracked commands. Confirm owned work has
  stopped without terminating/restarting the shared OpenCode service or affecting
  unrelated sessions/processes. Uncertain stopping holds the run for recovery.
- Setup failure, timeout or uncertain stopping preserves artifacts and prevents ready
  status. Secret values do not enter exported evidence.
- Report explicitly that execution is non-sandboxed. Directory tests establish
  correct routing, not filesystem/network/resource containment.

**Proof:** real OpenCode V2 parent/subagent directory canaries, clone independence,
effective-configuration verification and unapproved-override refusal, duplicate
launch, basic owned-session/command stopping with unrelated-session survival,
setup failure/timeout and redaction tests using trusted fixtures.

Add `tests/test_w2.py` with injected adapters/clocks/crashes, then a separately
authorized, opt-in real fixture exercise. Cover:

- Two clones with distinct canaries: parent and genuine subagent reads/writes/shell
  operations reach only their assigned clone during the routing exercise; the
  original checkout and neighbouring canary remain unchanged.
- Exact Git baseline/branch, independent metadata and no alternates/worktree links.
- Global/ancestor/project override discovery, changed effective role permissions,
  unavailable configuration identity and real role-tool denial.
- Duplicate calls, existing destination and ambiguous session/command creation.
- Interruption around preparation, cloning, configuration validation, session
  creation, command creation, collection and stop confirmation; no implicit relaunch.
- Setup/check failure, quiet timeout, late success and API-call deadlines.
- Parent/subagent/command descendant stopping, including a direct command parent
  exiting before its descendant, and unrelated-session/process survival.
- Evidence secret canaries, output-removal ordering and preserved failure artifacts.

The two-clone qualification exercises routing only; it does not authorize production
parallel dispatch or bypass the automatic capacity limits. Mocks cannot prove real
delegation, permission enforcement, directory binding or stopping.

**Exit:** record the tested source/profile/bundle/configuration/runtime/API identities
and pass the real routing, role-control and basic-stopping gates. Any uncertain gate
holds W3. A fixture pass is not ordinary project readiness, sandbox qualification or
authorization to implement a slice.

#### W2 assembly checkpoint — 2026-10-06 (not accepted)

Continuation after service restarts resumed from the existing W2 assembly, not the
archived M2 storage plan. No previously completed live storage probes were repeated.

- Assembled implementation: `routine/local_run.py`, `routine/opencode_local.py`,
  `routine/local_lifecycle.py`, and local entry-point changes in `routine/launcher.py`
  and `routine/cli.py`. Tests/fixtures: `tests/test_w2.py`,
  `tests/test_w2_adapter.py`, `tests/test_w2_clone.py`,
  `tests/test_w2_assembly.py`, `tests/w2_fixture.py`. Paths are relative to
  `linux/opencode-routine/`.
- The pre-existing read-only findings in
  `docs/review-findings-2026-10-05.md` recorded **601 collected, 583 passed,
  18 live skipped**, including **141 W2 tests**. Those observations are a prior
  checkpoint, not a substitute for final source-bound independent verification.
- Independent daemon-free verification: **601 collected, 582 passed, 19 skipped**;
  W2 subset: **141 collected, 140 passed, one skipped**; no failures/errors. Eighteen
  skips are gated live-image tests. The additional offline tagged-API test skipped
  because `/tmp/opencode/w2-input-evidence-k93yu_bl/v2.0.22-openapi.json` was absent;
  this is missing deterministic contract coverage, not a live-runtime skip or pass.
  No published/current API bytes were substituted for the pinned release.
- Exact full command (from the dotfiles root):

  ```sh
  env -u OPENCODE_ROUTINE_TEST_IMAGE -u OPENCODE_ROUTINE_COMPONENT_IMAGE \
      -u OPENCODE_ROUTINE_STORAGE_IMAGE \
      TMPDIR=/tmp/opencode PYTHONDONTWRITEBYTECODE=1 \
    python3 -B -m unittest discover -s linux/opencode-routine/tests -v
  ```

  Subset used the same command with `-p 'test_w2*.py'`. All **18** W1/W2 source/test
  hashes were unchanged before/after both runs and rechecked against this working
  tree on return. Canonical sorted `{path, sha256}` inventory identity, paths relative
  to the launcher package:
  `679ec25335a806f5460f993be24c6e3e38f911a6c1f3bc744de4e9a3258f4ec1`.
  Private logs, exact commands/counts and inventories:
  `/tmp/opencode/w2-independent-verification-m51AQuUE/`.
  README/docs are excluded from that code/test identity. The verifier reported that
  it could not find this plan; the parent directly confirmed it exists. Verification
  followed the supplied no-edit/no-live task instructions; it is not contract review.
- Fresh read-only W2 source review remains in progress. Its blockers/advisories and
  final disposition must be recorded before presenting completed assembly evidence.
- The package README now identifies the workflow-first local path and labels the
  retained M1/M2 sandbox documentation historical. README scope/link/typed-operation
  consistency checks and tracked whitespace checks passed. The current authorization
  does not permit landing untracked work, changing agent models/permissions, changing
  ignore rules or repairing unrelated global configuration.
- The configured Tester agent could not start because its configured model is
  unsupported with the current account. No agent configuration was edited; an
  independent general agent was assigned the same no-edit verification task instead.
- No real session/command launch, live sandbox opt-in, production-state mutation,
  host installation, infrastructure change, GitHub write or repository commit was
  performed by this continuation. The injected runtime is not a ready-made production
  connection/observer assembly and does not establish real OpenCode gates.

**Boundary:** W2 acceptance remains open. The separately approved exercise below
must establish real discovery/configuration, permissions, genuine delegation,
directory routing and owned-descendant stopping before W3 can proceed. Missing
visibility remains a blocker, not permission to weaken a gate or start a service.

#### Separately approved real W2 qualification — proposal, not execution

After deterministic assembly/review, request one bounded joined exercise under a
new disposable `/tmp/opencode/w2-real-qualification-*` root, against an explicitly
named **existing** approved shared service/connection reference. No automatic
service discovery/start/restart, host/global config edit or legacy role bundle.

1. Approve exact assembled source/test fingerprint, tagged/runtime API bytes,
   fixture baseline/profile/command identities and minimal fixture role/bundle.
   First inspect installed/service release identity and OpenAPI through the approved
   connection, and offline inventory of global inputs, all ancestors through `/`,
   clone/project definitions and overrides. Retain hashes, not raw secret/config
   values. If discovery is incomplete or executable inputs are unapproved, stop
   **before** any location/config request that could load them; propose separate
   setup/observability work instead of bypassing the gate.
2. Once discovery is approved, resolve location configuration/agents and compare
   source ordering, bundle and role permissions, plugins/MCP/skills/formatter/LSP
   identities. Demonstrate permitted and denied fixture tool actions and controlled
   override refusal. Merely receiving ordered config documents is insufficient.
3. Prepare two independent baseline clones with distinct canaries/branches/Git
   metadata. Bind parents and genuinely delegated children to their canonical clone
   locations; demonstrate read/write/shell routing and unchanged original/neighbor
   canaries. A shared project ID is not a routing failure or routing proof.
4. Run only exact approved harmless setup/check argv, including selected success,
   failure, quiet timeout and parent-exits-before-descendant fixtures. Retain exit,
   deadline, process start identity and bounded non-secret diagnostic counters.
   Repeat identical requests to prove no duplicate create/budget reset; interrupt
   selected intent/observed checkpoints to demonstrate held ambiguous outcomes.
5. Preserve diagnostics before command removal; request stop during an active
   lifecycle operation and confirm registered parents, real children, tracked
   commands and descendants stopped. Independently observe an expressly approved
   unrelated fixture session/process and shared-service identity surviving. If
   available APIs cannot establish descendant ownership/termination or effective
   controls, retain a blocker/hold, not an interrupt-acknowledgement pass.
6. Retain clones, immutable handoff and identity-bound redacted evidence. Report
   each actual gate/unknown and stop for the user's W2 decision. No W3, integration,
   production dispatch, GitHub writes, installation or repository commits follow.

Approval must identify the service connection, permitted discovery surfaces and
executable configuration inputs, fixture mutations/commands and any unrelated
canary session/process allowed for survival checks. Credentials remain references,
never supplied to planning/evidence. This proposal does not grant that approval.

### W3 — Local session → independently verified slice

**Deliver:** Orchestrator delegates to Builder, Tester and fresh-session Reviewer.

**Dependency:** consume W2-qualified location/configuration/stopping capabilities;
do not enable the real loop on copied prompts or mocked runtime evidence alone.

**Acceptance**

- All roles receive the full spec, ticket and explicit applicable criteria.
- Validate thin role contracts and the local skill snapshot/provenance against
  actual invocation behavior. Helpers remain optional, with Explore for local code
  discovery and Research for cited external evidence.
- Builder owns TDD, committed tests, scoped refactoring and clean commits.
- Tester executes checks/assesses coverage without product or committed-test edits;
  Reviewer is read-only. Validate actual configured tool restrictions and limits.
- Complete contribution range and final commit anchor accompany evidence/coverage.
- Missing checks, required criteria or blocking review findings prevent admission.
- Mutations invalidate relevant checks/review; passing stale evidence is rejected.
- Shared budget: two corrective passes after initial implementation; early stall
  escalation. Initial expected TDD failures are not repairs; do not weaken tests.
- Contract changes escalate. Orchestrator stops after its slice, with no mandatory
  Cleaner, Refactorer or Tester-owned repair loop.

**Proof:** real named-role delegation, missing criteria, prohibited tool requests,
post-review edits, test removal and repeated/cycling failure cases.

### W4 — Verified slice → verified local feature integration

**Deliver:** collect commits/evidence, prepare a local combined candidate, verify it
and atomically advance the feature branch only if its expected head is unchanged.

**Dependency:** own complete contribution-range admission and advance W1's operational
verified head only with the exact verified publication. Keep the approved initial
baseline immutable; subsequent claims use the newer verified feature head.

**Acceptance**

- Validate input identity, commit ancestry, complete range and exact-commit evidence.
- Worker `ready` is not merge authority. Verify the exact combined result before
  publishing; passing slices or a clean merge alone are insufficient.
- Serialized per-feature integration; stale head, failure or timeout leaves the last
  verified feature head unchanged. Keep failed candidates and diagnostics.
- Candidate checks/review and repository operations use the intended disposable
  local checkout. Avoid unintended Git hook/config execution during launcher-owned
  Git operations; this is hygiene, not sandbox protection for approved scripts.

**Proof:** conflicting changes, clean merge with failing combined behavior, forged
evidence, moved head and timed-out verification.

**Gate A:** one real OpenCode slice completes claim → local clone/session → Builder
implementation → independent tests/review → verified local integration, including
the corresponding negative cases. No sandbox qualification is required.

### W5 — Interruption → supervised stopping and deliberate recovery

**Deliver:** recover from durable local run checkpoints without duplicate workers.

W2 already qualifies basic owned-work stopping before W3. This milestone extends
that prerequisite with comprehensive interruption, supervision and recovery tests.

**Acceptance**

- Coordinator loss holds new dispatch/integration; existing workers remain supervised
  within budgets and results are collected.
- Identify owned sessions and tracked command/process trees. Stop only owned work;
  do not restart/terminate the user's shared OpenCode service or unrelated sessions.
- Confirm old execution has stopped before reassignment. Ambiguous status holds work.
- Preserve partial edits, commits/evidence and consumed repair/runtime budgets.
  Recovery uses fresh sessions with the recorded inputs/bundle; reverify final state.
- Defaults: 60-minute slice, 10-minute inactivity, 30-minute integration. Waiting for
  capacity is excluded; preparation is included. Quiet tracked commands may run until
  their deadlines; heartbeats alone are not progress.
- Explicit stop-feature halts automatic work, preserves verified publication and
  does not stop user QA. Exhausted budgets require approved extensions.

**Proof:** interruption around preparation/session start/commit/checks/collection/
candidate publication; process ownership, quiet commands and budget-preserving recovery.

### W6 — Approved project onboarding → readiness and GitHub traceability

**Deliver:** reusable setup skill, local-profile validation and launcher-managed PRs.

Extend the early fixture-only local profile through explicit schema/approval changes;
do not reinterpret existing fixture or sandbox authorizations as ordinary project
readiness. Keep concrete service, GitHub and QA mechanics scoped to this milestone.

**Acceptance**

- Discover existing stack/docs/commands/services/access; propose changes before any
  mutation. Approval remains required for setup/install/provisioning/config changes.
- Existing projects reuse conventions; new projects have approved bootstrap checks.
- Validate the setup and upstream alignment/spec/ticket skill handoffs, preserving
  human review of both spec and slice graph without duplicating their procedures.
- Required baseline checks pass unless the user approves a recorded narrow exception;
  exceptions are not passes and never cover new feature failures.
- Readiness pins revision/profile/bundle and validates real agents/tools, trusted
  setup, checks and applicable runtime services in a disposable clone.
- Record relevant host access and shared service/port risks; do not claim isolation.
- GitHub operations are idempotent, with slice PRs, final feature PR and exact verified
  remote publication tied to expected head. Failures remain recoverable.
- Workers do not manage PRs; protected-check proposals need setup approval. No final
  agent merge into `main`; state manual/admin enforcement limits.

**Proof:** new/existing fixtures, missing checks/exceptions, profile drift, unapproved
setup refusal, fake GitHub failures and a separately authorized disposable GitHub test.

### W7 — Approved graph → sequential delivery and bounded corrections

**Deliver:** adapt `implement-spec` for Coordinator scheduling; run one slice at a time.

**Acceptance**

- Contract consumers wait for verified owner integration and start from that newer
  feature baseline. Cross-feature prerequisites wait for approval/merge into `main`.
- Single-slice mode dispatches one. Default batch selects at most three ready slices
  once without refill. Explicit whole-feature mode may dispatch newly ready work.
- Hold affected dependency chains on failure/disagreement, not unrelated authorized
  work. Already-running affected results are provisional, not integrated.
- One implementation-only reconciliation run per conflict group; no recursive
  correction or renamed groups to reset budgets. Changed contracts need approval.
- Full-spec review detects ticket omissions; at most one completion-correction slice
  per feature, not one per finding. Reverify/review combined corrections.
- Coordinator uses approved artifact reads and typed launcher operations, not product
  edits or arbitrary shell work. Test actual harness restrictions and state their limits.

**Proof:** two independent slices plus a contract owner/consumer, no-refill behavior,
authorized scope, bounded reconciliation, omissions and contract-change escalation.

**Gate B:** sequential delivery passes workflow authorization, failure, recovery,
integration and correction tests before enabling parallel dispatch.

### W8 — Dependency-ready slices → bounded parallel local delivery

**Deliver:** parallel scheduling without changing earlier acceptance contracts.

**Acceptance**

- Three workers per feature by default; three host-wide workers including corrections.
- Separate host-wide cap of three integration checks; serialized integration per feature.
- Atomic capacity/claims and deliberate recovery; capacity waiting consumes no runtime.
- Independent feature Coordinators compete safely; batches still do not refill.
- Concurrent clone/session directories are correct and commits integrate once.
- Project commands/services have explicit port/path/resource coordination or run
  sequentially where shared resources cannot safely coexist. No implied network isolation.
- User QA is outside automatic pools, with combined host load visible for tuning.

**Proof:** simultaneous features, capacity saturation/queueing, cancellation, stale
publication, recovered reservations and shared-service/port collision handling.

### W9 — Integrated feature → user-owned QA and acceptance handoff

**Deliver:** synchronize with latest `main`, reverify/full-spec review and present the
exact finished feature for human QA and final merge.

**Acceptance**

- Handoff includes verified commit/main baseline, full-spec coverage, check/review
  evidence, PRs, risks/deviations, structural summary and short QA checklist.
- QA uses explicit start/status/stop for the identified verified state; browser and
  non-browser projects are supported. Do not start a preview automatically.
- User-started QA persists until explicitly stopped, outside worker/check pools and
  unaffected by automatic cleanup/stop-feature.
- If `main` advances, hold acceptance, synchronize/reverify, refresh handoff/QA and
  request renewed approval. Approval cannot follow an arbitrary moving branch.
- User performs final merge into `main`; no deployment.
- Retain successful generated checkouts until acceptance; failures/interruption need
  explicit cleanup. Preserve specs, history, summaries, PR references and evidence.

**Proof:** stale main/approval, reviewed-state QA startup, user-owned lifetime,
cleanup boundaries and optional finished-feature Recaper.

## 4. Validation and acceptance

Use deterministic contract tests with fake clocks/adapters and injected crashes,
then real local OpenCode/clone/session tests on trusted disposable fixtures, then
separately authorized end-to-end GitHub and QA exercises. Mocks cannot establish
actual role delegation, directory routing, cancellation or integration behavior.

Bind evidence to tested source/profile/bundle/runtime/commit identities. Keep missing
or failed checks visible. Historical M2 passes are sandbox component evidence, not
local workflow acceptance; deferred sandbox requirements are not reported as passed.

| Legacy finding | Workflow proof |
|---|---|
| S1 Criteria visibility | W1/W3 full planning package and explicit criteria |
| S2 Post-verification mutation | W3/W4 exact-commit invalidation/rechecks |
| S3 Competing status authorities | W1 one ledger; derived views |
| S4 Incomplete recovery | W5 interruption at every checkpoint |
| S5 Shared state clobber | W1/W5 locks, ownership and atomic writes |
| S6 Incomplete commit range | W3/W4/W6 start/final anchors and ancestry |
| S7 Oscillating failures | W3/W5 failure history, stall detection and fixed budgets |
| S8 Excess permissions | W2/W3/W7 actual role/tool restrictions with honest host-access limits |
| S9 Shrinking tests | W3/W7 coverage preservation |
| S10 Prompt-only scope | W3 final-diff review against ticket/constraints |
| S11 Unbounded execution | W5/W7/W8 time, repair, correction and capacity limits |
| S12 Inconsistent phases | W3/W7 one role-based loop |
| S13 Diagram/tool errors | Shared guidance; verify actual diagram/tool references |
| S14 Tester-owned repairs | W3 Tester reports; Orchestrator sends repair to Builder |

## 5. Next approval boundary

The earlier session authorized W1 compatibility/adaptation and disposable W1 tests
only, and stopped at presentation for W1 acceptance as recorded above. The user
has now accepted that reviewed W1 implementation and its nonblocking advisories,
and explicitly authorized **W2 source/test assembly and disposable trusted fixtures**.

Present assembled W2 deterministic evidence, independent verification/fresh review,
remaining gates and the concrete joined qualification proposal. Do not mark W2
accepted or start the real exercise without separate approval. Real workflow
workers/sessions/commands, live sandbox tests, GitHub writes, host installation,
infrastructure changes, production-state mutation and repository commits remain
outside the current authorization. W3 and later remain unauthorized. The earlier
documentation-only revision itself authorized none of those operations.
