> **Historical copy (2026-10-06)** of root `docs/brainstorming.md`. Mixed decision/exploration record copied intact; later one-slice approval supersedes its W1–W9 implementation order.
> Original root note remains ignored and untouched. Paths written as `docs/...` below refer to original drafting locations; use [the package history index](../README.md) for relocated files.

# Multi-orchestrator workflow — brainstorming notes

**Status:** workflow-first scope revision captured (2026-10-05); replacement plan
drafted for review. The current
sandbox deferral below supersedes the earlier sandbox-required v1 decisions.
`docs/alignment.md` carries the corresponding contract amendment; remaining notes
preserve exploration and decision history, not competing execution rules.
**Starting point:** `docs/loop-logic.md` (current-state analysis).

## Current revision — workflow first, sandbox as a later project

**Decision (2026-10-05):** the user wants sandboxing disabled for the workflow's
initial implementation. Sandbox implementation is a separate project to be
rethought and planned **after implementing the workflow**, not completed first or
carried forward as the current design by default.

- Remove sandbox qualification as a prerequisite for implementing or validating
  the workflow. The current M2/PID diagnosis is no longer the active priority.
- Focus on planning handoffs, agent responsibilities, implementation, independent
  testing/review, bounded repairs, coordination, verified integration and human QA.
- Keep existing sandbox source, qualification records and retained evidence. This
  decision does not authorize deletion, migration, daemon/firewall changes or
  rollback of previously approved host configuration.
- Non-sandboxed execution is trusted local execution, not security isolation.
  Separate branches/checkouts and role permissions do not establish filesystem,
  network, credential or resource containment against untrusted code.
- Existing approval, acceptance/evidence, repair/runtime/concurrency, retention and
  final human-merge contracts remain unless explicitly revised. Sandbox-specific
  enforcement/qualification requirements are deferred, not reported as passed.
- No production access or deployment is newly authorized. Keep secrets out of
  planning documents and reports; do not claim credentials are isolated on a shared
  host merely because sandboxing is disabled.

**Checkout decision:** the user confirms **one independent clone per slice** for
trusted local execution, rather than Git worktrees. Each slice has a distinct
directory, branch and its own `.git`; its Orchestrator and subagents must operate
in that clone. Start from the recorded verified feature baseline. Avoid shared
alternates or shared Git metadata; transfer the completed commit range through the
controlled integration path. Separate clones prevent ordinary Git-state coupling,
not access to other host directories or shared ports/services/credentials.

**Still to resolve:** qualify concrete local session mechanics and review the
replacement implementation plan. Validate actual subagent/tool working directories
rather than assuming the parent session's directory propagates. Do not build a
general backend abstraction or plan the future sandbox during this revision.

**Session boundary:** documentation changes only. No sandbox runtime has been
disabled in code, no worker has been launched and no infrastructure changed.

### Session outcome — replacement plan drafted

The user requested simplified implementation milestones while retaining the
existing coordination, verification, integration and QA decisions, and explicitly
requested this brainstorming document remain the record of changes.

**Accepted decisions**

1. Implement the workflow first without sandboxing.
2. Keep one independent clone per slice, not worktrees or one shared working directory.
3. Treat sandboxing as a separate project, to be rethought/planned afterwards.
4. Preserve the established non-sandbox workflow contracts rather than reopen them.
5. Preserve this brainstorming history and existing sandbox work/evidence.

**Proposed replacement milestones** — detailed acceptance/tests are in
`docs/implementation-plan.md`; drafting them is not implementation authorization.

| Milestone | Observable outcome |
|---|---|
| W1 | Reuse/adapt historically accepted M1 claims/authorization for local execution |
| W2 | Prepare an independent clone and prove real local session/subagent tool routing |
| W3 | Complete one slice with Builder, independent Tester/Reviewer and bounded repairs |
| W4 | Verify the combined candidate before advancing the feature branch |
| Gate A | Accept one real single-slice path and its failure cases, without sandbox gates |
| W5 | Supervise stopping and recover deliberately with preserved work/budgets |
| W6 | Approve project onboarding/readiness and establish idempotent GitHub traceability |
| W7 | Deliver dependency-ordered work sequentially with bounded reconciliation/omission correction |
| Gate B | Accept sequential failure/recovery/authorization behavior before parallel dispatch |
| W8 | Deliver parallel slices within the existing capacity limits and coordinate shared runtime resources |
| W9 | Present the exact verified full feature for user-owned QA and final human merge |

**What changed**

- Archived the sandbox-required implementation plan at
  `docs/archive/implementation-plan-sandbox-2026-10-04.md`, preserving its checkpoint
  and qualification history. W identifiers avoid reusing historical milestone names.
- Replaced `docs/implementation-plan.md` with the workflow-first proposal. Sandbox
  diagnosis/qualification no longer blocks the agent loop, integration or scheduling.
- Updated `docs/alignment.md` to trusted local execution: local clone/session
  lifecycle, approved host commands, local candidate verification and non-sandboxed QA.
- Retained feature-bundle snapshots but removed worker-image packaging as a dependency.
- Kept deterministic state/claims, spec/ticket hashes, role separation, commit-bound
  evidence, verify-before-publish, repair/runtime/capacity limits and human final merge.
- Updated `docs/CONTEXT.md` to distinguish independent clones, trusted local
  execution and QA environments from security sandboxes.

**Deferred, not passed:** hard resource containment, storage/quota/retained-layer
inspection, network/firewall/proxy/DNS restrictions, credential broker/isolation,
container-local provider configuration, container execution qualification and future
sandbox architecture. Existing app-service Compose use may remain project-specific
setup; it does not make agent execution sandboxed.

**Risks and validation priorities**

- Independent clones separate Git state, not host access. Require trusted projects
  and state ambient credential/network/file exposure honestly.
- Local role permissions must be tested, but are not an adversarial security boundary.
- Parent/subagent directories and owned session/command cancellation must be proven
  on the actual OpenCode V2 runtime. Never stop the user's shared service as a shortcut.
- Ports, services and writable runtime paths can collide despite independent clones;
  coordinate them or serialize incompatible project commands.
- Historical M1 acceptance is reusable evidence, not automatic approval of adapted
  local interfaces. Historical M2 evidence cannot establish local workflow acceptance.

**Next step:** review the replacement plan, then separately authorize W1 adaptation.
No implementation, cleanup, extraction, provisioning or runtime rollback occurred.

**Documentation verification:** a separate read-only consistency review found no
material scope/contract contradictions. Two coverage clarifications were applied:
W1–W5 use approved trusted fixtures rather than bypass ordinary project readiness;
the accepted locally owned skill scope/provenance is explicitly mapped into W2/W3,
W6 and W7. No application tests were run for this documentation-only revision.
A browser-only milestone diagram was opened for review; no diagram file was saved.

### Diagram clarification — build sequence versus running workflow

The user observed that the milestone diagram looked very sequential and asked
whether the Coordinator retained a role. Clarified that W1–W9 describe the order
of building/accepting capabilities, not a sequential runtime architecture.

- Coordinator still selects authorized ready slices, dispatches through the launcher,
  tracks results/PR lifecycle, coordinates integration/corrections and prepares QA.
- Finished runtime supports multiple concurrent one-slice Orchestrators in separate
  independent clones; per-feature integration remains serialized and verified.
- Integration can unblock consumers, but the default bounded batch still does not
  refill. Continued ready-work dispatch requires the existing explicit whole-feature
  mode or a new authorized launch; the diagram does not expand dispatch authority.
- Opened a second browser-only diagram showing runtime fan-out, gated integration
  and authorized scheduling feedback. No diagram file or source code was written.
- Added the build-order/runtime distinction directly to the implementation plan.

### Alignment review — basic stopping moves into W2

**Accepted (2026-10-05):** qualify basic owned-session/command stopping in W2,
alongside real parent/subagent directory routing, before enabling W3's real
implementation loop. Prove that owned work stops without terminating/restarting
the user's shared OpenCode service or affecting unrelated sessions/processes.
Uncertain stopping holds the run for deliberate recovery.

W5 retains comprehensive crash supervision, checkpoint recovery and budget
preservation. This moves an essential prerequisite earlier; it does not authorize
implementation or change execution scope. Updated the implementation plan and
alignment contract; no source/runtime changes or tests performed.

### Alignment review — effective configuration is a W2 gate

**Accepted (2026-10-05):** W2 must verify the effective role/tool configuration
against approved inputs, accounting for relevant global, ancestor and project
configuration inherited by OpenCode V2. Record its non-secret identity. Copying
the approved agent/skill bundle alone does not establish what runs. Unapproved
overrides or unverifiable effective configuration hold the run before W3.

Updated the implementation plan and alignment contract. No source changes,
configuration changes, worker launches or runtime tests occurred. The proposed
wrong-implementation fixture and clearer operational status remain recommendations,
not separately accepted requirements.

## Desired role and outcome

The user wants to act primarily as **product owner / manager and QA**, rather
than supervising each implementation step:

- Discuss projects, features, and fixes with the Brainstormer and Aligner.
- Tell multiple Orchestrators to start working.
- Review and check the resulting work afterwards.

The direction is greater execution autonomy with clear handoffs and reviewable
results. The exact approval gates and autonomy boundaries remain undecided.

## Topics to explore (not prioritized)

### Parallel execution and isolation

- Run multiple Orchestrators simultaneously.
- Each Orchestrator works on its own slice branch, unlike the current setup.
- Provide sandboxing for each execution environment.
- Make communication between sessions clearer and cleaner.

**Open questions:** what counts as adequate isolation; how slices are assigned;
how dependencies, shared changes, and integration are coordinated; what information
sessions exchange and where it lives.

### Agent capabilities and supporting roles

- Identify important missing skills; the specific skills are not yet listed.
- Consider a dedicated Research subagent.
- Consider an Explore subagent available to every other agent for codebase
exploration and understanding.

**Open questions:** boundaries between research and exploration; when agents
delegate; what outputs are reusable across sessions.

### New versus existing projects

- Account for both new projects and work in existing codebases.

**Open questions:** which onboarding, discovery, planning, and validation steps
should differ between these project types.

### Product-owner handoff and QA

- Preserve discussion with the Brainstormer and Aligner before execution.
- Allow several Orchestrators to execute without constant user supervision.
- Make completed work easy for the user to inspect and validate afterwards.

**Open questions:** what makes work ready for autonomous execution; what requires
escalation to the user; whether QA happens before or after integration; how work
is presented for review.

## Existing reliability concerns

The 14 findings in `docs/loop-logic.md` remain the baseline for redesign. Parallel
execution should not obscure unresolved criteria visibility, state ownership,
resume behavior, post-refactor verification, commit tracking, or execution budgets.

## Pending inspiration

The user has two videos that inspired this direction. The first was supplied as
a transcript and is summarized below; the second is still pending. No external
verification of the speaker's tools or performance claims has been performed.

## Video 1 — extracted ideas

**Source:** user-supplied workshop transcript; speaker introduces himself as Matt.
These are the speaker's proposals, not yet decisions for this workflow.

### Human responsibility versus autonomous execution

- Keep idea development, alignment, and task slicing human-in-the-loop.
- Delegate well-scoped implementation to an away-from-keyboard (AFK) workflow.
- Retain human QA and code review to check intent, usability, and taste.
- Treat discovery as iterative: research and prototypes can send work back to
  alignment rather than following a rigid one-way sequence.
- Feed QA findings back into the backlog as new issues, including while other
  implementation work is running.

**Relevant timestamps:** 26:36–27:09, 52:37–53:30, 1:00:32–1:03:46,
1:12:35–1:13:33, 1:34:50–1:35:13.

### Destination and journey are separate artifacts

- A PRD records the destination: problem, solution, user stories, implementation
  and testing decisions, and explicit out-of-scope items.
- A dependency-aware issue board records the journey, rather than a single
  sequential multi-phase plan.
- Issues should be independently pickable when their blockers are resolved and
  distinguish AFK work from work requiring human involvement.
- Prefer thin vertical slices with observable end-to-end behavior over completing
  database, API, and UI layers separately. Human review of slicing still matters:
  even a vertical-slicing instruction produced a horizontal first task in the demo.

**Relevant timestamps:** 28:38–35:09, 39:32–47:01, 49:37–51:38, 58:17–58:47.

### Context management and supporting agents

- Keep always-loaded instructions small; load specialized skills on demand.
- Delegate codebase exploration to a subagent with its own context and receive
  focused summaries in the parent session.
- Favor fresh implementation/review contexts with explicit inputs over relying
  on a long conversation and repeated compaction.
- The demo supplies issues and recent commits to a fresh execution session.

**Caution:** the speaker's approximately 100k-token / 40% "smart zone" boundary
is a heuristic, not an established universal threshold. Fresh contexts require
reliable handoff artifacts and do not by themselves guarantee better results.

**Relevant timestamps:** 3:00–10:56, 17:35–18:26, 37:24–38:33, 54:16–55:12,
1:05:31–1:06:15, 1:28:09–1:29:42.

### Parallel execution and integration

- Select a set of dependency-ready issues from the backlog.
- Run each issue in its own branch/worktree inside a Docker sandbox.
- Review resulting commits in a separate step/context.
- A merger agent integrates branches and addresses integration/type/test failures.
- The speaker demonstrates a sequential run first, then describes parallel
  orchestration via a TypeScript library called Sand Castle.

**Not resolved by this transcript:** atomic task claiming, session communication
protocols, state ownership, complete sandbox security boundaries, shared runtime
resources, merge authority, or safe limits on autonomous integration fixes.

**Relevant timestamps:** 55:12–56:05, 1:29:48–1:32:40.

### Quality, skills, and architectural ownership

- Use red–green–refactor TDD in small increments and run tests/type checks as
  feedback loops; independently assess whether tests cover the intended behavior.
- Give implementers access to coding standards on demand; supply reviewers with
  the applicable standards explicitly.
- Favor deep modules: simple public interfaces hiding substantial functionality,
  with meaningful tests at their boundaries. This is not simply a preference for
  larger files or fewer modules.
- Retain human understanding of module responsibilities and interfaces while
  delegating implementation details.
- Assess architecture/testability improvements in existing codebases.
- Prevent old PRDs/issues from being mistaken for current truth by closing,
  archiving, or removing completed execution documents.

**Candidate skills mentioned:** grilling/alignment, writing a PRD, PRD-to-issues
vertical slicing, TDD, improving codebase architecture. Research/prototyping,
code review, and QA are also workflow capabilities to consider; not all are
presented as named skills in the transcript.

**Relevant timestamps:** 1:06:37–1:11:27, 1:14:14–1:23:08,
1:23:19–1:25:07, 1:28:09–1:32:40.

## Implications to explore for our routine

- Separate backlog-wide coordination from each slice's execution Orchestrator.
- Consider dependency-aware scheduling instead of numbered sequential slices.
- Define a self-contained slice handoff so fresh sessions can read criteria,
  constraints, relevant code context, and verification expectations (addresses S1).
- Distinguish automated verification, independent code review, and human QA.
- Validate both the final slice state and the integrated result, including changes
  made by refactoring or merge conflict resolution (extends S2).
- Design explicit communication and state ownership rather than sharing one
  mutable `current-slice.toml` across workers (relates to S3–S5).
- Define a review-ready deliverable so parallel throughput does not simply move
  the bottleneck to the user's QA queue.
- Explore project onboarding: existing-code discovery/testability assessment
  versus establishing architecture and feedback loops in a new project.

**Ideas not accepted wholesale:** skip PRD review because summarization is assumed
reliable; use a fixed context threshold for all models; assume passing tests or a
clean merge proves acceptance; let a merger make unrestricted semantic changes.
These need risk-based decisions, not adoption by analogy.

## Decisions

### Review unit: finished feature, with slice PRs

The user prefers to approve the **finished feature**, with **slice PRs** available
for traceability and deeper inspection. Routine approval of every slice is not
the intended workflow.

- Each independently reviewable slice has its own branch and PR.
- Related slices are assembled on a feature integration branch.
- A final feature PR presents the integrated result for the user's QA and approval
  before reaching `main`.
- Slice PRs retain requirements, changes, verification evidence, and review history
  without making the user a mandatory gate at every slice.

### Automatic slice integration, human feature approval

The user authorizes agents to automatically merge slices into the **feature
integration branch** once their checks and independent review pass. Escalate
blockers or unresolved risks rather than requiring routine slice approval.

- This authority is limited to feature integration; it does not authorize merging
  the final feature into `main` or deploying it without user approval.
- The integrated result must be verified again, including any changes introduced
  during conflict resolution. Slice-level success alone is insufficient evidence
  for final feature acceptance.

**Still open:** which agent owns/serializes integration, exact automated gates,
handling dependent slice PRs, boundaries on conflict-resolution changes, and
concrete escalation rules.

### Execution autonomy: adapt the route, preserve the destination

The user agrees that the technical plan is guidance, not a cage. Acceptance
criteria and explicit constraints are the execution contract.

- If an implementation detail is unclear, agents inspect the code, choose a
  reasonable approach, document it, and continue.
- If the technical plan is wrong, agents may revise the approach while preserving
  agreed behavior, scope, and architectural constraints. Verify the result and
  record the deviation.
- If product intent is unclear or requirements conflict, escalate to the user
  rather than inventing an answer or silently weakening acceptance criteria.
- Changes to scope, architecture, security boundaries, or dependencies affecting
  other slices require a recommendation brought back for user approval.
- Agents should challenge incorrect criteria or constraints rather than blindly
  implementing them, but cannot silently rewrite that contract.

### User-dispatched, one-slice Orchestrators

**Superseded dispatch decision:** the initial preference was user-owned direct
dispatch with no additional AI coordinator. The user has since selected a
Coordinator using `implement-spec` as the starting point (see below). The original
one-slice worker boundary remains; the coordinator's batch/feature stopping policy
still needs agreement.

- Each Orchestrator takes one dependency-ready, unclaimed slice and works in its
  own branch/worktree and sandbox.
- Each Orchestrator **stops after its slice**; it does not automatically claim
  another. Further dispatch is owned by the Coordinator within user-authorized
  bounds, which remain to be defined.
- A successful run completes the agreed checks, independent review, and permitted
  integration into the feature branch, then reports its result. A blocked run
  escalates rather than moving on to another slice.
- Five starts is an example of desired concurrency, not an agreed fixed cap.

**Required design safeguards:** atomic slice claiming and serialized updates to
the feature integration branch. These can be deterministic coordination mechanisms
rather than a coordinating AI agent; their implementation remains undecided.

**Proposed no-work behavior:** if no unblocked, unclaimed slice is available,
report that and stop rather than duplicate work. Exact claim/release/recovery
semantics still need agreement.

### Sandbox execution model: host launcher, container-local agents

The user accepts the proposed runtime model:

- A **host-side launcher** claims the slice, prepares its checkout, starts its
  Docker Compose environment, collects results, and manages cleanup. This is
  infrastructure, not an additional coordinating AI agent; the user owns dispatch.
- Each slice has its own **container-local OpenCode service**, configuration,
  and state. Its Orchestrator dispatches subagent sessions through that service,
  so their filesystem and shell tools execute within the slice sandbox.
- Subagents share their slice's sandbox; a separate container per subagent is
  not required. Different slices remain isolated from each other.
- Project-specific Compose services provide the app, database, and other runtime
  dependencies as needed. Resource isolation should match the project rather than
  provision a full stack for every task unnecessarily.
- Workers have **no host Docker socket**. Container lifecycle and controlled,
  serialized feature integration remain host-side responsibilities.
- Merely containerizing the app while running the agent service on the host does
  not sandbox agent execution. Host-executing MCP integrations must be assessed
  explicitly so they do not bypass the intended boundary.

**Checkout detail still open:** Git worktrees reference shared repository metadata.
Mounting only a worktree may break Git; exposing host repository metadata weakens
isolation. A separate clone per sandbox with controlled host import of commits was
recommended as a possible simpler starting point, but has not been selected.

**Implementation validation still required:** container-local launch and subagent
behavior, scoped credentials, configuration/state locations, mounts, networking,
artifact transfer, integration verification, resource limits, and cleanup/recovery.

### Trial: review-ready feature preview

The user agrees to try a completed-feature handoff with a **running preview
environment** and a **short QA checklist**, making the integrated feature ready
for immediate inspection rather than handing over only a diff.

- The preview represents the integrated feature, not an arbitrary slice checkout.
- Provide access/run details and a brief checklist tied to agreed acceptance
  criteria, alongside the final feature PR and slice PR references.
- For projects without a browser UI, adapt the preview to the appropriate runnable
  CLI/API/demo environment; do not assume every project needs a web preview.

**Still open:** preview ownership/lifetime, safe test data and credentials, resource
limits, and cleanup after approval or rejection. This is an agreed workflow trial,
not a claim that a preview or launcher has been implemented or started.

### Initial backlog: local

The user chooses a **local backlog for the first version**, rather than GitHub
Issues as the authoritative backlog. This does not change the agreed slice PRs
and final feature PR review structure.

- Local feature specifications capture product intent, acceptance criteria,
  constraints, and exclusions.
- Local slice records capture execution-ready work and dependencies, with branch,
  PR, and result references as work progresses.
- Runtime coordination must support atomic claims and recovery separately from
  product documentation; ordinary Markdown edits are not a locking mechanism.

**Still open:** exact file layout/schema, authoritative status ownership,
transactional runtime store implementation, and reconciliation between operational
state and any human-readable backlog view. Do not introduce competing status
fields across documents and runtime storage without a defined ownership model.

### Implementation readiness

The user prefers to **implement the routine first**, rather than select a pilot
feature now. Remaining contracts to resolve before planning implementation:

- Claim/release/recovery semantics and authoritative runtime state.
- Sandbox checkout strategy (worktree versus separate clone), scoped credentials,
  and container-local tool execution validation.
- Integration ownership/serialization and conflict-resolution boundaries.
- Exact slice and integrated-feature verification/review gates.
- Agent responsibility boundaries and treatment of existing phases.
- Project onboarding/profile for setup, services, checks, and preview.
- Concurrency, retry, runtime/cost limits, and escalation behavior.
- Feature completion, preview lifetime, and cleanup behavior.

Address the existing S1–S14 findings as part of this design, not as problems to
carry unchanged into parallel execution. The next phase should resolve execution
contracts and produce an implementation plan; no pilot is required to continue.

### Updated decision: Coordinator using `implement-spec`

The user explicitly chooses a **Coordinator agent** above slice Orchestrators,
using Matt Pocock's **`implement-spec` skill as the starting point**. This supersedes
the earlier no-coordinator dispatch preference.

- The Coordinator can dispatch one worker or several dependency-ready workers.
- Each slice Orchestrator still owns one slice and stops when that slice finishes
  or escalates. It may delegate to its Builder, Tester, Reviewer, Explore, etc.
- The Coordinator owns backlog-wide scheduling and integration coordination;
  a host-side execution adapter must actually start workers inside their sandboxes.
- Native subagent creation alone does not establish a container boundary.
- Preserve local backlog, slice PRs, automatic gated feature integration, and human
  approval of the finished feature before `main`.

**Not yet decided:** authorize a single slice, a bounded batch, or an entire feature
per Coordinator launch; concurrency cap; resume/recovery contract; how skill-driven
scheduling is connected to deterministic dispatch and gates.

**Sandcastle status:** investigated as a candidate infrastructure library, not yet
selected or installed. See `docs/sandcastle-investigation.md` for pinned source
findings, fit, and gaps. SQLite was a recommendation only and has not been accepted.

### Execution backend decision: Compose plus a small launcher

The user accepts **Docker Compose plus a small deterministic host-side launcher**
as the first-version execution backend. Sandcastle is **deferred**, not required
by `implement-spec`, and has not been installed.

- The Coordinator uses an adapted `implement-spec` dispatch step to invoke the
  launcher, rather than assuming ordinary subagent creation creates a sandbox.
- Compose runs the container-local OpenCode worker and any project-specific
  app/database services, with explicit networks, volumes and resource limits.
- The host launcher handles checkout/environment preparation, worker launch,
  result collection and lifecycle; controlled integration and recovery still need
  precise contracts.
- Keep the launcher narrow rather than recreating a general sandbox framework.
  Reconsider Sandcastle only if lifecycle needs justify the extra dependency.

This selects an execution backend, not the still-open backlog/runtime schema,
checkout strategy, concurrency/stopping policy, or exact quality gates.

## Launch contract — agreed direction

The user accepted the proposed high-level launch/result/failure contract and the
recommended batch default. The details below are the agreed direction, not yet a
finalized schema or implementation.

### Coordinator to launcher

- Feature/slice IDs and a unique run ID.
- Versioned references to the local feature spec and slice ticket, including
  acceptance criteria, constraints, and pre-agreed testing seams.
- Explicit feature integration branch and exact starting commit.
- Project profile: sandbox setup/services, verification and preview commands.
- Authorized limits: runtime, retries and resources; scoped credential references,
  never secret values in backlog documents or reports.

The launcher validates the request and exclusively claims the slice before
preparing its checkout and Compose environment. Repeated requests must not start
duplicate workers. Backlog paths must be made accessible inside the sandbox;
host-only paths are not sufficient handoffs.

### Worker to launcher to Coordinator

- Run/slice identity, branch, starting and final commit anchors.
- Outcome: ready-for-integration, blocked, or failed. Ready is not integrated or
  human-accepted.
- Acceptance coverage, executed checks and independent review results, tied to the
  exact final commit; missing checks/review must not be reported as passed.
- Evidence/log references, short summary, plan deviations, unresolved risks and
  escalation questions, plus slice PR reference when available.

Worker reports are evidence to inspect, not unconditional merge authority. A
host-controlled gate admits the branch to serialized integration, followed by
verification of the resulting feature commit.

### Failure and recovery behavior

- No ready work: report and stop; do not bypass dependencies.
- Invalid request or setup failure: report actionable diagnostics, without marking
  the slice complete.
- Product ambiguity or contract-changing fix: stop/escalate with a recommendation.
- Failed checks/review: bounded repair within the agreed contract; if still failing,
  report failure and do not integrate.
- Timeout/crash: preserve checkout/evidence and mark interruption for explicit
  recovery; do not silently reassign while a worker might still be alive.
- Integration failure: preserve a diagnostic state, block dependent dispatch and
  do not mark the slice integrated. Exact rollback/recovery behavior remains open.

Coordinator launch scope is recorded below. Concurrency cap and timeout values
remain separate, unresolved decisions.

### Coordinator dispatch scope: batch by default

- Default to a **bounded batch** of up to N dependency-ready slices, then stop;
  do not automatically refill the batch with newly unblocked work.
- Support an explicitly requested single-slice run.
- Whole-feature mode must be explicitly requested; it can keep dispatching newly
  ready work until completion or a blocker, within the concurrency limit.
- Every slice Orchestrator still owns only one slice.

**Accepted initial limits:** up to **3 slices per batch** and **3 concurrent
workers**, configurable per project. Batch size limits total dispatch for that
launch; concurrency limits simultaneously running workers. Explicit whole-feature
mode can dispatch further slices as slots become available while retaining the
configured concurrency cap.

**Still open:** timeout/retry values and exact request/result representation. Five
parallel starts was previously an example, not the accepted numerical default.

## Additional inspiration: skills main-flow tutorial

The user supplied a second workshop/tutorial transcript explaining installation,
per-project setup and the main skills flow. This is transcript evidence, not a
newly inspected repository version. Its 38-skill count, `CONTEXT.md` naming and
combined `tickets.md` example differ from the previously inspected 37-skill
snapshot (`GLOSSARY.md`, one file per local ticket). Reconcile conventions during
implementation rather than mixing versions or replacing the existing glossary.

### Confirmed direction

- Local Markdown is a supported tracker choice; no database is implied by that
  choice. Atomic execution coordination/recovery remains a separate requirement.
- Configure tracker, labels and domain-document conventions per project, for both
  new and existing codebases.
- Preserve alignment, spec synthesis and ticket slicing in one planning context
  when practical. Start fresh execution contexts from the resulting artifacts.
- Multi-session work uses a destination spec plus bounded tickets; small work can
  use `implement` without manufacturing a large decomposition.
- Perform independent standards/spec reviews in subagent contexts and compare the
  finished feature against its full spec, not only its slice tickets.

### Accepted workflow refinements

- The user accepts thin agent wrappers around the selected skills rather than
  duplicating their procedures in every prompt. Agent contracts define authority,
  inputs/outputs and escalation; skills define the working method. Exact phase
  consolidation remains to be planned.
- A slice can reference shared feature requirements instead of duplicating them,
  but the worker must receive/read both and have explicit applicable criteria.
- Full-feature spec review remains required even when individual slices pass:
  decomposition can omit requirements.
- Small work can be one slice without unnecessary decomposition; larger work
  becomes a dependency graph. Keep sandbox and quality gates in either case.

### Still to resolve

- Decide skill distribution/version pinning for sandbox workers. A global host
  installation or symlink does not ensure container availability.
- Treat the speaker's context-token limits and installation-load claims as
  environment/model-specific, not universal execution thresholds.

The tutorial does **not** change the accepted Coordinator/`implement-spec`,
Compose/launcher, one-slice workers, batch limits, PR/QA structure or autonomy
boundaries. It does not settle checkout strategy, locks, runtime recovery or gates.

### Checkout decision: independent clone per slice

The user selects **a separate clone per slice**, accepting the disk/setup overhead
and confirming sufficient disk space. This resolves the previous checkout choice.

- Each worker has its own checkout and Git metadata, not a worktree referencing
  the host repository's shared `.git` directory.
- Start from an explicitly recorded feature integration commit and use a distinct
  slice branch.
- Do not use a shared object-directory arrangement that defeats the intended
  independence (for example, shared-clone alternates pointing into the host repo).
- The host-controlled integration path imports the worker's commits; transfer,
  authentication and clone creation details remain to be designed.

Independent clones improve Git isolation but do not replace container permissions,
runtime service isolation, exclusive task ownership or serialized integration.

### Repair budget: two attempts, with early stall escalation

The user accepts **up to two repair attempts after failed checks or independent
review**, in addition to the initial implementation attempt.

- If failures remain after that budget, stop and escalate with evidence.
- Stop earlier if the same failure repeats without meaningful progress.
- This budget does not authorize changes to the agreed product/scope/architecture
  contract; those still escalate immediately under the autonomy rules.

**Still open:** how a repair attempt is counted across check/review stages, how
progress/failure signatures are measured, and runtime/idle timeout values.

### Initial timeout defaults

The user accepts **60 minutes per slice, including repairs**, and **10 minutes
of inactivity before interruption and recovery**, both configurable per project.

- Timeouts preserve work and diagnostic evidence and do not mark the slice done.
- Recovery must establish that the prior worker is stopped before reassignment.

**Still open:** precise timer start/stop boundaries and the definition of activity.
Long-running tests or setup may be legitimately quiet; absence of streamed text
alone must not be assumed to prove a stalled worker.

### Coordinator ownership: one active Coordinator per feature

The user accepts **one active Coordinator per feature**, while allowing
Coordinators for different features to run concurrently.

- Enforce feature ownership in host-side coordination rather than relying only
  on a prompt convention.
- Serialize updates to each feature integration branch and preserve exclusive
  slice ownership within that feature.
- Recover ownership deliberately after interruption; do not start a replacement
  while the previous Coordinator or its workers may still be active.

**Still open:** host-wide resource/concurrency limits across different features,
cross-feature dependencies, and synchronization with changes to `main`.

### Initial integration gate

The user accepts the following gate **to start with**, subject to refinement from
experience:

- Account for every slice acceptance criterion with evidence or an explicit
  unresolved gap. An unresolved required criterion prevents integration.
- Pass project-defined tests, lint/type checks, and build where applicable.
- Complete independent review with no unresolved blocking findings.
- Tie evidence to the exact final slice commit admitted for integration; any
  subsequent mutation requires renewed relevant checks/review.
- Verify the resulting feature commit again after integration.
- Report missing checks explicitly; absence of evidence is not a passing result.

**Still open:** per-project required commands and coverage, blocking review
severity definitions, and authorized handling of genuinely unavailable checks.
The initial gate does not replace final full-spec review or human feature approval.

### Project readiness before execution

For both new and existing projects, the user accepts **pausing for a
project-readiness assessment when tests or check commands are missing**.

- Identify verification/setup gaps and propose the necessary setup work.
- Do not silently weaken the integration gate to keep execution moving.
- New projects need initial feedback-loop/environment setup; existing projects
  need discovery of the commands and coverage already present before proposing
  replacements.

**Still open:** readiness/profile format, approval and scheduling of setup work,
and explicitly justified not-applicable checks for nonstandard project types.

### Coordination state: host-only files and OS-backed locks

The user accepts **host-only execution state files with OS-backed locks** for the
initial single-host workflow; SQLite is not selected.

- Track feature ownership, exclusive slice claims, checkpoints and integration
  separately from local Markdown requirements.
- Workers must not be able to edit host coordination/lock state directly.
- Define atomic state updates, consistent locking and interrupted-run recovery
  in the implementation plan. Markdown status views must not become a competing
  writable runtime authority.

## Proposed project setup process (under discussion)

The user asks whether new/existing projects need a setup process to support this
flow. Recommended answer: yes, separate one-time workflow installation from
per-project onboarding, with readiness validation before execution.

### One-time workflow installation

Provide the Coordinator/slice agent contracts, pinned skills, launcher, container
tooling, and default limits once. This is distinct from project-specific setup.

### Per-project onboarding

1. Discover existing repository conventions, domain documentation, toolchain,
   setup/check commands, runtime services, credentials requirements and Git/PR
   configuration. Never assume an existing project needs a replacement stack.
2. Confirm choices with the user and capture a project profile: trusted setup,
   checks, Compose configuration, sandbox mounts/network policy, skill availability,
   resource limits, branch/PR conventions, and preview/QA lifecycle.
3. Configure local spec/ticket conventions and domain doc references, adapting
   `setup-matt-pocock-skills` rather than duplicating it blindly.
4. Validate a disposable independent-clone environment: dependency install,
   container-local named agent/tool execution, baseline checks, applicable runtime
   health checks and preview access, then cleanup.
5. Mark ready or report explicit gaps and proposed setup work. Readiness applies
   to the tested revision/profile and needs reassessment when relevant inputs change.

**New projects:** agree stack/architecture first, then approved bootstrap work
establishes minimal scaffolding and feedback loops. Do not require nonexistent
tests as a precondition for creating the initial test infrastructure; give bootstrap
work explicit checks for the infrastructure it creates, then validate readiness.

**Existing projects:** reuse current commands/services/docs, record baseline
failures, and propose targeted missing pieces. Do not silently treat existing
failures as passes or relax the accepted gate.

**Still open:** profile schema/location, setup-work approval contract, credential
delivery, and lifecycle ownership. This is a proposed onboarding process, not a
claim that project setup has been implemented or a final approved design.

### Project setup approval gate

The user explicitly requires project setup to **propose its changes for approval
before applying them**.

- Discovery produces a proposed setup/change set and validation plan.
- Do not apply scaffolding, configuration changes, dependency installation,
  provisioning or other mutating setup actions before approval.
- Once approved, apply only the agreed changes and validate readiness; additional
  scope or newly required changes return for approval.
- Existing project configuration and credentials must not be overwritten silently.

Exact profile format and setup implementation remain open; nothing has been
installed or executed by this ideation session.

## Analysis: skills v1.2.0 release overview

**Inputs:** user-supplied release-video transcript, official release/changelog,
tagged skill sources and documentation landing page. The official release is
dated **2026-08-05**; inspected tag tree SHA:
`2ffb184ffbb752faa664c0b204f3c9241b1428e9`.

Sources:
- https://github.com/mattpocock/skills/releases/tag/v1.2.0
- https://github.com/mattpocock/skills/blob/v1.2.0/CHANGELOG.md
- https://github.com/mattpocock/skills/blob/v1.2.0/skills/productivity/grilling/SKILL.md
- https://github.com/mattpocock/skills/blob/v1.2.0/skills/engineering/wizard/SKILL.md
- https://github.com/mattpocock/skills/blob/v1.2.0/skills/engineering/resolving-merge-conflicts/SKILL.md
- https://www.aihero.dev/skills

### Highest-value implications

1. **Dependency-aware interview rounds.** Ask independent decisions together;
   hold dependent questions until prerequisites are resolved. This directly
   addresses the repetitive "sounds good" tail of our current discussion. Adopt
   as a recommended Aligner refinement, not as permission to combine dependent
   decisions or silently accept defaults. The active Brainstormer's interaction
   policy and final Aligner configuration still need deliberate reconciliation.
2. **Thin prompts and authoritative references.** `writing-for-agents` covers agent
   instructions and pointed-at docs, reinforcing our accepted wrapper approach.
   Cache rationale/gotchas, not redundant copies of readily discoverable scripts
   and config; a project profile should identify required checks/policy while
   pointing to their implementations.
3. **Human-only setup steps via `wizard`.** Useful for onboarding credentials or
   provider dashboards. It complements project setup; it does not replace Compose,
   launcher setup, approval or readiness validation.
4. **Shared language plus `wait-what`.** Explicit project terminology reduces
   confusing cross-session reports. `wait-what` repairs an unclear message; it is
   not a communication protocol or a substitute for clear contracts.
5. **Versioned distribution matters.** Managed auto-updating Claude plugins and
   editable skill copies are different maintenance models. Recommend pinned,
   reviewed copies for our adapted flow and reproducible worker images rather
   than silent mid-feature changes. No installation/distribution choice was made.

### Compatibility and security boundaries

- Codex `agents/openai.yaml` sidecars mark user-invoked skills with
  `policy.allow_implicit_invocation: false`. That is Codex metadata, not proof of
  identical invocation or context-load behavior in OpenCode. Verify against our
  actual harness; do not infer hidden context or available calls from another UI.
- A user-invoked skill is not inherently a permission boundary. Coordinator
  authority and host gates must still enforce what work is authorized.
- A locally executed wizard can keep entered secrets out of model prompts, but
  being deterministic does not by itself make a generated script safe. Review
  destination paths/commands, avoid secret logging/tracing and unnecessary
  credential mounts, and preserve setup approval.
- `to-questionnaire` is optional stakeholder collaboration support: useful when
  someone else owns the missing decision, not necessary for our solo starting flow.

### Findings beyond the video

- The v1.2.0 tag contains **35** `SKILL.md` files; our earlier **37-skill ranking**
  remains correct for its separately pinned main snapshot. Do not treat these
  inventories as the same version.
- **`implement-spec` is absent from v1.2.0**, although it exists in the main
  snapshot we selected. Pinning the whole bundle to v1.2.0 would not provide our
  agreed Coordinator baseline. Keep an explicit selected source/version for it.
- Tagged setup/local-tracker guidance confirms **one file per ticket** under
  `.scratch/<feature>/issues/` and `spec.md`, not the tutorial's combined
  `tickets.md` example. This is a useful proposed convention, not yet our finalized
  profile/schema.
- The release also revises prototype preservation and research resolution, and
  emphasizes scoping architecture work to active pain points rather than blanket
  refactoring. These fit human-owned decisions and evidence-based discovery.
- The tag includes **`resolving-merge-conflicts`**, absent from our earlier pinned
  main inventory. Its instructions say "Always resolve; never --abort", choose
  between incompatible intents, and stage everything. **Do not adopt it unchanged**:
  incompatible product/architecture intent must escalate under our accepted rules;
  stage only authorized integration changes and retain safe stop/recovery behavior.

### Overall effect

No change to the chosen Coordinator/Compose/launcher architecture, independent
clones, local backlog, batch limits or QA boundaries. The release improves how we
align, write instructions and handle human-only onboarding. It does not implement
our runtime isolation, locks, recovery or integration gates.

**Status:** analysis/recommendations captured; no new adoption decisions, skills
installed, scripts executed, or application source changes.

These notes are not yet an implementation plan or a complete technical design.

## Skills follow-up

The user considers the second video less relevant and instead requested a ranking
of all skills in `mattpocock/skills`. See `docs/skills-ranking.md` for the complete
37-skill snapshot ranking, highlighted starter capabilities, dependencies, and
gaps that still require workflow design. These are recommendations, not adoption
decisions; no skills have been installed.

## Alignment decisions — parallel planning safeguards

### Shared-contract dependency rule

The user requires shared contracts to be established before parallel dispatch of
dependent slices. If a shared contract needs changing, assign that change to one
owning slice and block its consumer slices until the owning change is integrated.
Do not dispatch multiple slices to independently redefine the same shared contract.

This is a mandatory planning safeguard, not a guarantee that implementation will
reveal no missed assumptions or integration conflicts.

### Unexpected contract disagreement: pause the affected dependency chain

If implementation reveals that an agreed shared contract is wrong, pause the
contract-owning slice and its affected consumers and escalate with a proposed
correction. The user chooses to pause only affected/dependent slices, not the
entire feature. Genuinely unrelated slices may continue within the existing run
authorization; the pause does not grant a larger batch or new scope.

Handling of already-running workers is refined below: pause does not necessarily
mean terminating them. New affected dispatch and integration remain held.

### Finish provisionally; Coordinator-dispatched reconciliation

The user authorizes already-running affected workers to finish within their
existing budgets rather than requiring immediate termination. Their outputs are
provisional and must not enter feature integration while the conflict is unresolved.
New affected consumer slices remain blocked; unrelated work may continue.

The Coordinator may automatically dispatch a dedicated reconciliation slice when
the conflict is implementation-only and resolution preserves all approved
contracts. This is explicit authority for corrective dispatch beyond the original
batch, not for unrelated additional slices or expanded feature scope. Changes to
approved interfaces, behavior, architecture or other explicit constraints still
require user approval before reconciliation proceeds on that changed basis.

The reconciled result requires renewed affected checks and independent review;
passing evidence for the old outputs is not automatically valid for the changed
result. The existing serialized integration and post-integration verification
requirements continue to apply.

The user limits automatic reconciliation to one run per affected conflict group,
with the normal 60-minute runtime limit and up to two repair attempts. Remaining
failure or a required contract change escalates; the Coordinator must not launch
recursive reconciliation automatically or bypass the limit by renaming the group.
Precise conflict-group identity and provenance/state representation remain to be
resolved.

### Slice PR management: Coordinator lifecycle, host-side operations

The user accepts the following responsibility split:

- Slice Orchestrators produce commits, verification evidence and independent review
  results; they do not manage PRs or receive PR-management credentials.
- The Coordinator manages slice PR lifecycle, tracks results, schedules integration
  and dispatches authorized reconciliation.
- The deterministic host launcher creates/updates slice PRs from worker results,
  enforces integration gates and serializes Git operations into the feature branch.
- The user approves the final feature PR before it may reach `main`.

Provider/authentication details and exact PR metadata/state transitions remain
open.

### Integration is verified before publishing the feature head

The user accepts local staging of the combined result before advancing the
feature integration branch. The feature branch remains at its last verified
commit while integration checks run.

- The launcher prepares a candidate merged commit in a disposable checkout,
  retaining it through a local Git reference. A published candidate branch or
  additional PR is not required.
- Verify the exact combined commit before advancing the feature branch to it.
  Individually passing slice checks do not establish that the combination passes.
- If verification fails, preserve the candidate and diagnostic evidence without
  advancing the feature branch. Apply the agreed affected-work hold and bounded
  reconciliation/escalation rules.
- Serialize integration and do not publish a different, unverified result if the
  feature head changes during verification.

This resolves the earlier candidate-before-publish proposal; final full-spec review
and human QA/approval remain separate requirements.

### Synchronize with main before final QA, not continuously during slice work

The user accepts late synchronization with `main`. Active slice work stays on its
recorded feature starting baseline rather than being continuously disrupted by
other features reaching `main`. Slices may still start from later verified commits
within their own feature as dependencies integrate.

Before presenting the finished feature for human QA, synchronize its integrated
result with the latest `main`, repeat integration checks and full-feature spec
review, and present the resulting verified state. The verify-before-publish rule
also applies to this synchronization.

The final merge strategy remains unresolved. Further changes to `main` after the
QA handoff are governed by the approval rule below.

### Human approval is tied to the reviewed state and main baseline

The user accepts that QA approval applies to the exact verified state presented
for review, not to arbitrary later versions of the feature branch. If `main`
advances during QA or between approval and final merge, hold that merge,
synchronize and reverify the feature, refresh the preview and request renewed
approval with a short change summary. Old approval must not authorize an updated,
unreviewed combined result.

The final merge must enforce the reviewed commit/main-baseline anchors rather
than rely on a check made earlier; provider-specific implementation remains open.

### Initial host-wide worker cap

The user accepts an initial configurable host-wide cap of three active worker
sandboxes across features, including reconciliation workers. Keep the existing
per-feature cap as well. Authorized work waits for capacity rather than letting
each feature independently consume three simultaneous workers.

The user intends to revisit the cap based on observed load. Resource usage should
be visible during the trial; concrete reporting and resource budgets for runtime
services, integration checks and previews remain to be specified. Queue fairness
remains open; the slice timer excludes capacity waiting as agreed below.

### Slice runtime timer starts at environment preparation

The user accepts that time waiting for an available host capacity slot does not
consume the 60-minute slice budget. The timer starts when the launcher begins
preparing the checkout/environment and includes setup, implementation, checks and
repairs. Do not expire a slice merely because authorized work was queued.

Exact completion/result-collection boundaries and the inactivity signal still
need definition. Host integration is a separate operation from worker completion;
its own timeout/resource budget remains open.

### Quiet tracked commands are not agent inactivity

The user accepts that tracked setup/test/build commands may remain quiet until
their command deadline. Apply the 10-minute inactivity timeout when the agent
stops progressing without such an active command; absence of streamed text alone
does not establish inactivity. Service heartbeats alone do not count as agent
progress. The overall 60-minute slice cap still applies during quiet commands.

Project command deadlines and concrete progress events/observability remain to
be specified. A crashed or expired command must not indefinitely suppress idle
detection.

### One shared repair budget across checks and review

The user accepts a shared maximum of two corrective implementation passes after
the initial implementation, across failed checks and independent review findings.
One pass may address several failures together. Running checks again or moving
between test and review stages does not reset the budget or consume an additional
repair merely because multiple commands/findings are involved. Expected failing
tests during initial TDD are not repair attempts.

Existing early-stall escalation and contract-change approval rules still apply.
The budget must not be reset by launching a fresh subagent for the same work.

### Refactoring belongs in implementation, not a mandatory post-verification phase

The user removes the mandatory Refactorer phase from the redesigned execution
loop. The Builder performs scoped refactoring within its normal red-green-refactor
cycle before final verification/review. Independent review may request improvements,
which follow the shared corrective-pass budget when treated as repair work.

A separate Refactorer may remain available for explicitly targeted work; it is
not automatically invoked after every slice. All subsequent code mutations still
require renewed relevant checks/review at the exact final commit. This is a design
decision only; existing agent source files have not been changed in this session.

### Commit ownership and deterministic artifact collection replace mandatory Cleaner

The user removes the mandatory Cleaner phase from the redesigned loop. The
Builder owns clean commits. The launcher collects final commit anchors, logs and
verification/review evidence rather than invoking an agent that adds commits or
moves documents after verification.

Retention and cleanup must use explicit lifecycle rules. Do not let an agent
infer that requirements, current planning documents or diagnostic evidence are
disposable. Concrete retention/lifecycle defaults remain to be agreed. Existing
Cleaner source is unchanged; any optional/manual future role is not decided here.

### Builder owns tests; Tester independently verifies

The user removes Tester's scaffold mode from the redesigned loop. The Builder
writes and maintains committed tests using TDD. The independent Tester executes
agreed checks, assesses acceptance coverage and reports verification gaps without
editing application code or weakening committed tests. Missing coverage returns
to the Builder rather than allowing the Tester to redefine success.

The slice Orchestrator retains execution/repair control. Running verification
commands may create normal runtime/build artifacts; this is not authority to
modify the product or the acceptance contract. Concrete permissions and optional
scratch diagnostic mechanisms belong in the implementation design.

### Dedicated independent Reviewer

The user accepts adding a dedicated read-only Reviewer role, run in a fresh
session separately from Builder and Tester. It reviews compliance with approved
requirements and applicable coding/architecture standards. Findings return to
the slice Orchestrator for bounded repairs; the Reviewer does not edit code or
own the implementation loop.

The existing independent-review gate and exact-commit evidence requirements
apply. Review severity/blocking definitions and model/skill configuration remain
to be finalized; no Reviewer source file is created during alignment.

### Blocking review findings versus advisory improvements

The user accepts blocking integration for unmet acceptance criteria,
correctness/security defects, violations of explicit constraints or required
project standards, and missing verification needed to establish required behavior.
Style preferences and optional improvements are advisory unless explicitly
required by project policy.

A blocking finding must identify the violated requirement/standard or concrete
risk; an unexplained preference for another implementation is insufficient.
Advisory findings do not authorize extra scope or mandatory repair work. The
implementation must retain unresolved findings in the result/PR rather than
silently dropping them.

### Baseline checks green by default; exceptions require explicit user approval

The user clarifies that required baseline checks must be green before dispatch
unless the user explicitly authorizes otherwise. Onboarding may propose a narrow
exception for a reproduced, pre-existing failure unrelated to the planned work;
agents cannot grant that exception themselves.

An approved exception must remain visible as an exception, not be reported as a
passing check. It does not authorize new failures or failures affecting the
feature. Record its specific failure/scope and approval so it cannot become a
blanket permission to ignore a failing command. Missing or unavailable required
checks still require readiness assessment and a user decision, not an inferred
pass or automatic exception.

### Integration verification is sandboxed

The user requires integration checks to run in a disposable container rather
than execute repository-provided test/build/setup scripts directly on the host.
The launcher performs host-side Git/PR operations, coordination and container
lifecycle, but does not expose its PR credentials to repository scripts.

Host-side Git operations must not become a bypass for repository-provided hooks
or equivalent executable configuration. Concrete protection, mounts, credential
scopes, integration-check timeouts and shared resource accounting remain to be
designed. Container isolation is a required execution boundary, not a claim of
protection from every possible container escape.

### V1 sandbox credentials and data: no production access

The user accepts prohibiting production credentials and production data in v1
worker, integration and preview environments. Only explicitly approved
development/test credentials and model-provider access may be supplied. Do not
mount the user's full home directory or SSH agent into these environments.

Use scoped credential references rather than secret values in specs, tickets or
reports. Project onboarding must establish required access; credential injection,
redaction, network restrictions and revocation details remain part of the design.
No deployment or production-access capability is implicitly granted by feature
execution or approval.

### QA sandbox is on-demand, not automatically left running

The user supersedes the earlier trial requirement to deliver an already-running
feature preview. Instead, the feature handoff provides a way to start the
integrated feature sandbox for testing. Do not automatically leave runtime
services running merely because a feature becomes review-ready.

Preserve the agreed exact verified feature state, final feature PR, slice PR
references and short acceptance-linked QA checklist. The proposed 24-hour
automatic-preview lifetime was not accepted. Exact start/stop interface, QA
sandbox capacity accounting and post-start lifetime remain to be agreed.

### User-started QA sandboxes do not consume worker slots

The user rejects counting QA sandboxes against the three-slot worker pool,
because QA sandbox startup is initiated by the user. Keep QA runtime capacity
separate from automatic worker dispatch. This does not remove the sandbox's
configured resource limits or justify hiding its contribution to observed host
load. Limits/lifecycle for user-started QA environments remain to be specified.

### User owns QA sandbox start/stop lifecycle

The user accepts explicit start, status and stop actions for the on-demand QA
sandbox. Once started, it remains running until the user stops it. No
agent-controlled shutdown or automatic expiry applies by default, including
merely because the feature is approved or rejected. Resource usage remains
visible and configured container limits still apply.

Start actions must identify the reviewed feature commit rather than silently
follow a later moving branch head. If renewed QA is required, make the change of
reviewed state explicit. Recovery across host restarts and test-data persistence
details remain implementation/lifecycle questions.

### Coordinator crash: finish supervised workers, hold new dispatch and integration

The user accepts that after a Coordinator crash, the host launcher continues to
supervise already-running workers within their existing budgets and collects
their results. Do not start new slices or integrate their results until deliberate
Coordinator recovery. Preserve completed and partial work rather than duplicate
or discard it because the parent session disappeared.

Host-side ownership/recovery must establish the prior Coordinator's status and
each worker's actual state before proceeding. This does not authorize a second
active Coordinator or reassign a slice whose worker may still be alive.

### Interrupted-slice recovery preserves work and consumed budgets

The user accepts deliberate recovery in a fresh agent session using the preserved
checkout and durable checkpoints. Retain consumed repair attempts and runtime
budget; fresh sessions do not automatically reset either. If the budget is
exhausted, additional time/attempts require explicit user authorization.

Confirm the prior worker is stopped before reassignment. Reverify the recovered
final state before integration rather than trusting a recorded intermediate
phase or stale evidence. Do not discard partial edits by default or rely on a
long prior conversation as the only recovery input. Concrete checkpoint schema
and safe validation of dirty worktrees belong in implementation planning.

### Trial: pinned agent/skill bundle packaged in the worker image

The user agrees to try packaging reviewed, version-pinned skills and agent
definitions into the worker image. Record the bundle version for each run. Update
deliberately rather than silently changing instructions mid-feature; do not rely
on host-global installations or symlinks for container availability.

The Coordinator's adapted `implement-spec` must retain an explicitly selected
source revision because it is absent from the v1.2.0 release inventory. Exact
starter skill selection, transitive dependencies and maintenance/distribution
layout still need to be finalized. This is approval of the trial design, not an
instruction to install or build anything during alignment.

### On-demand Research role; Explore handles local code discovery

The user accepts an on-demand Research subagent for external documentation and
technical evidence. Its output includes citations and explicit uncertainties.
Local codebase discovery belongs to Explore. Neither helper is mandatory on every
slice. Research findings that require changing the approved execution contract
return to alignment rather than silently changing the implementation scope.

Exact helper availability/permissions, reusable finding locations and freshness
tracking remain to be specified. No Research agent source is created in this
alignment session.

### Planning remains upstream; user reviews spec and slice graph

The user confirms that planning is outside the execution loop and chooses to
review both the feature spec and the high-level slice/dependency graph before
handoff. Approve them together upstream, including acceptance criteria and
testing expectations. A subsequent instruction to run a batch/slice/feature
authorizes execution of that approved package without an additional redundant
planning approval prompt.

The Coordinator schedules approved work; it does not repeat planning or invent
requirements. Dispatch references the approved artifact versions. Contract
changes still return to alignment, while the explicitly authorized technical-only
reconciliation exception does not require routine reapproval of its dispatch.

### Preserve the feature spec; archive superseded planning discussion

The user accepts retaining the authoritative feature spec through execution and
QA, including final full-spec review. Archive superseded brainstorming/alignment
discussion instead of deleting it after planning approval. Workers receive
explicit references to current approved documents; archives are historical
context, not a competing instruction or runtime status authority.

This supersedes the current Planner directive to delete `docs/brainstorming.md`
and `docs/alignment.md` and treat only `docs/plan.md` as downstream truth. Exact
directory layout and post-acceptance archival still belong in the implementation
design. Existing Planner source has not been edited in this alignment session.

### V1 final merge into main is performed by the user

The user accepts personally approving and merging the final feature PR into
`main` for v1. Agents stop at the review-ready handoff; automatic merge authority
remains limited to gated feature integration. Do not infer permission for the
launcher to perform the final main merge or deployment from a feature launch.

The reviewed-state/main-baseline approval rule still applies. Provider checks or
repository protections must make stale readiness/approval visible and prevent an
ordinary stale merge where enforceable; the implementation must state any limits
to enforcement of user/admin actions rather than claim the launcher controls
every possible manual merge path.

### V1 PR hosting: GitHub only

The user accepts GitHub-only PR hosting for v1. Keep feature specifications and
slice tickets local; GitHub PRs provide review/integration traceability, not the
authoritative requirements backlog or host runtime store. Other providers are
deferred rather than adding a general hosting framework to the initial launcher.

GitHub authentication, required checks, branch protections and compatibility with
each project's existing merge conventions must be established through approved
onboarding. Do not silently rewrite those repository settings.

### Coordinator has a narrow host interface, not unrestricted host execution

The user accepts restricting the Coordinator to read access to approved planning
and results plus a narrow deterministic launcher interface for dispatch, status,
recovery, PR management and integration. It cannot edit application code or
execute arbitrary host commands to bypass worker isolation.

Host state and credentials remain launcher-owned. Interface validation and
permission enforcement must be designed for the actual OpenCode harness; a
prompt-only instruction is not sufficient containment. Authorized technical-only
reconciliation still follows this interface rather than granting general host
write/shell authority.

### Recaper is an optional finished-feature walkthrough

The user accepts keeping Recaper interactive and on-demand, with the finished
feature as the default review unit rather than an arbitrary latest slice. The
normal feature handoff includes a short structural summary; deeper walkthroughs
and diagrams are requested when useful and are not mandatory execution gates.

Recap inputs identify the reviewed feature, spec and exact commit range rather
than selecting whichever slice archive happens to be newest. The recap preserves
human architectural understanding without changing code or replacing QA.

### Integration checks have a separate host-wide cap of three

The user rejects sharing worker capacity with automatic integration checks and
chooses a separate host-wide cap of three simultaneous integration-check
environments. Keep the host-wide worker cap of three (including reconciliation
workers) independently. Per-feature integration remains serialized even when
different features verify candidates concurrently.

User-started QA sandboxes remain outside both automatic pools. Load reporting
must expose the combined resource usage; the two caps permit up to six automatic
environments, plus user-started QA runtimes. Individual container/project limits
and integration timeout defaults remain to be specified.

### Integration-check budget: 30 minutes by default

The user accepts a configurable default of 30 minutes per integration-check run.
Exclude time waiting for its capacity slot; include environment preparation and
verification. On timeout, preserve diagnostics and do not advance the feature
branch. Timeout is not a successful check or automatic authorization for an
unbounded rerun.

### V1 host support: Linux first

The user accepts validating/supporting v1 on Linux first. Keep Compose and project
profile design reasonably portable, but macOS support is deferred until separately
tested; the repository's existing macOS dotfiles do not establish launcher/runtime
compatibility. Multi-host/distributed execution remains outside the accepted
single-host coordination model.

### Initial skill scope accepted; user-owned copies with provenance notes

The user accepts the proposed initial scope: `grill-with-docs`, `to-spec`,
`to-tickets`, `tdd`, `code-review`, `handoff`, `research`, `writing-for-agents`,
`implement-spec`, and necessary setup/transitive dependencies.

The user explicitly does not want those skills tied to their upstream sources.
Maintain locally owned/adaptable copies with a note describing their origin,
rather than an upstream runtime dependency, submodule or managed update link.
This refines earlier recommendations to pin selected upstream sources: provenance
is information, not an ongoing source/distribution constraint. No bulk installation
of unrelated skills is authorized, and no installation occurs during alignment.

The user accepts immutable snapshots of the locally owned agent/skill bundle
when a feature starts. Later edits apply to future features rather than silently
changing instructions mid-feature. Record the local bundle identity per run and
use it during recovery. This preserves execution consistency without coupling
the owned copies to upstream distribution or updates.

### Explicit feature cancellation stops automatic execution and preserves work

The user accepts a stop-feature action that immediately halts new dispatch and
integration and stops the feature's active worker/integration-check containers,
preserving work and diagnostics. This differs from accidental Coordinator loss,
where already-running workers may finish under supervision.

Cancellation does not undo already-verified feature integrations and does not
stop a user-started QA sandbox unless explicitly requested. Retain checkpoints,
consumed budgets and ownership evidence for deliberate recovery; ensure a
container is actually stopped before allowing reassignment. A raced atomic
publish already committed before cancellation is recorded, not silently rolled
back as if it never happened.

### Full-spec omissions: one bounded corrective slice per feature

The user authorizes the Coordinator to dispatch one bounded corrective slice per
feature when full-feature review identifies omitted approved requirements despite
passing planned slices. Use the normal 60-minute limit and shared maximum of two
repair attempts. Correction must preserve approved contracts; contract changes
or remaining failure escalate.

This is explicit corrective authority beyond the original batch, separate from
implementation-conflict reconciliation. It is not one new slice per finding or
permission for a chain of completion repairs. Repeat full-feature verification
and spec review of the corrected result before calling it QA-ready.

### Network access is approved per project; host/LAN and cross-slice access blocked

The user accepts allowing only project-approved external access needed for
providers, dependencies and research. Block host/LAN access and cross-slice
connections by default. Project-specific development exceptions require explicit
onboarding approval and cannot introduce prohibited production access.

Containers still need their own project runtime services and controlled result
transfer. The implementation must validate effective network restrictions rather
than assume a distinct Compose network establishes host/LAN isolation. Required
proxy/firewall/DNS policy and install privileges must be proposed through the
approved setup process; they are not silently granted by this requirement.

### Automatic-environment cleanup and evidence retention

The user accepts stopping worker/integration-check containers once results are
safely collected. Keep successful checkouts until the feature is accepted, then
remove their generated environments. Preserve failed/interrupted checkouts until
explicit cleanup. Retain specs, summaries, PR references and verification evidence
rather than discarding the audit/review history with the heavy runtime artifacts.

Do not touch user-started QA sandboxes under automatic cleanup. Retention does not
authorize logging secrets or keeping production data. Concrete evidence archival,
disk quotas and restart/recovery packaging remain implementation details; storage
pressure must not silently override preservation requirements.

### V1 excludes additional monetary controls and cost accounting

The user places workflow-level billing/cost tracking and additional monetary
limits outside v1, relying on an existing provider/account limit. Do not add a
second cost-control system or require cost-accounting integration for readiness.
This is not an independently validated claim that provider billing can never
exceed an expected amount.

Keep the agreed concurrency, runtime and repair bounds. Host/container CPU,
memory and disk/load visibility remains separate from excluded monetary tracking.

### Project onboarding is a reusable setup skill, not a mandatory Setup agent

The user chooses a reusable project-setup skill invocable with any suitably
authorized interactive agent, rather than adding a mandatory dedicated Setup
agent. It discovers conventions/gaps, proposes the profile/change set, waits for
user approval, applies only approved changes and validates readiness. It supports
new and existing projects upstream of execution.

Loading the skill does not grant permissions: a read-only Reviewer or restricted
Coordinator remains restricted. Do not use skill invocation to bypass host
execution controls, setup approval or the sandbox boundary. An optional wrapper
could be added later if useful, but it is not required in v1.

### Cross-feature dependencies wait for main

The user accepts waiting for a prerequisite feature to be approved and merged
into `main` before dispatching a dependent feature, which then starts from the
updated baseline. Independent features may still execute concurrently. V1 does
not implement cross-feature branch stacking or a cross-feature dependency
scheduler; record the prerequisite as a dispatch blocker instead of silently
building against another feature's unapproved branch.
