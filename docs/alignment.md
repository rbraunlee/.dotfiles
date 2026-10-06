# Alignment — multi-orchestrator workflow

**Status:** long-term target, with the first-trial order approved 2026-10-06.
**Active sequence:** [workflow-plan.md](workflow-plan.md) proves one approved slice
before extending the launcher. The contracts below describe the longer-term
workflow, **not** prerequisites already met or a mandate to build W1–W9 first.
**Basis:** the alignment interview and dated decision/regression notes retained on
`experiment/opencode-routine-w1-w2-checkpoint` under
`linux/opencode-routine/docs/workflow/`. **Terminology:** [CONTEXT.md](CONTEXT.md).

## Scope amendment — sandbox deferred (2026-10-05)

The user disables sandboxing for the initial workflow implementation and makes it
a separate project to be rethought and planned after the workflow is implemented.
This amendment supersedes earlier requirements for container-local execution,
containerized integration/QA, hardened
network/credential isolation, enforced container resource quotas, worker-image
packaging and sandbox qualification as a readiness or execution prerequisite.

The initial workflow uses trusted local execution with **one independent clone
per slice**, confirmed by the user. Each has a distinct directory, branch and Git
metadata, without shared alternates. The slice Orchestrator and its subagents must
operate in that clone, starting from the recorded verified feature baseline; the
controlled integration path transfers the completed commit range. Concrete local
session/tool-directory behavior still needs validation. No security containment of
host files, credentials, network or resources may be claimed. Role restrictions and
exclusive state ownership remain workflow requirements, but their enforceable
limits on a shared host must be stated.

Preserve the planning/authorization, one-slice worker, independent verification and
review, bounded repair/time/concurrency, serialized verify-before-publish, recovery,
retention, PR and human QA/final-merge contracts **as longer-term targets**. For S0,
use only the narrower manual one-slice gate in [workflow-plan.md](workflow-plan.md):
no host launcher, Coordinator, durable ledger, multi-slice scheduling, GitHub PR
automation or recovery framework is required. These gates are deferred for S0,
not satisfied or discarded. No production access or deployment is authorized;
secret values remain excluded from planning and reports.

Existing sandbox code and evidence are preserved as historical inputs, not the
approved design for the future project. No host rollback, cleanup or infrastructure
changes follow from this amendment. The old sandbox-required plan and the
subsequent W1–W9 launcher sequence are **historical** on the experimental branch
(`linux/opencode-routine/docs/sandbox/` and `docs/workflow/`, respectively).
W1 acceptance does not qualify W2; M2 and its isolation gates remain unresolved.
Neither plan authorizes an S0 run. This document does not change runtime code.

## Current workflow contract

No S0 run or prompt rewrite has occurred. The existing agent role bodies still
describe the legacy loop; adapt the Orchestrator/Builder/Tester and add a fresh
read-only Reviewer **after this cleanup**, before any separately approved trial.
Check actual role access and clone directory routing. On OpenCode v2.0.22,
`planner`/`tutor` restrictions resolve from singular `permission:` maps while the
current V2 documentation describes `permissions:` arrays: recheck effective rules
on upgrade, never infer them from spelling alone.

## 1. Intended outcome

The user acts primarily as product owner and QA: discuss intent upstream, approve
the spec and slice graph, authorize execution, then inspect the finished feature.
Avoid routine supervision and approval of individual slice implementations.

First prove one bounded approved slice in a trusted disposable pilot project;
then consider the smallest automation justified by observed friction. Disposable
fixtures and end-to-end validation remain necessary before claiming the eventual
routine works. The sections below describe that longer-term target, not S0 gates.

V1 is single-host, Linux-first and GitHub-only for PR hosting. macOS, distributed
execution, Sandcastle and other PR providers are deferred.

## 2. Upstream planning and authorization

- Brainstorming, alignment, spec synthesis and slicing stay outside execution.
  Preserve one planning context where practical; execution starts from artifacts,
  not the accumulated conversation.
- The user reviews and approves both the feature spec and high-level slice graph,
  including acceptance criteria, constraints, exclusions and testing expectations.
- A subsequent run instruction authorizes that approved package without another
  redundant planning approval prompt.
- Specs and slice tickets are a local backlog. GitHub PRs are traceability/review
  records, not the authoritative requirements tracker.
- Prefer thin vertical slices. Small work may be one slice; do not manufacture a
  large decomposition. Shared requirements may be referenced rather than copied,
  provided each worker receives the feature spec and explicit applicable criteria.
- Establish shared contracts before dispatching their consumers. Give each shared
  contract change one owning slice; consumers wait for its verified integration.
  Do not dispatch slices to independently redefine the same shared contract.
- A feature depending on another feature waits until its prerequisite is approved
  and merged into `main`, then starts from that updated baseline. Cross-feature
  branch stacking and dependency scheduling are outside v1.

## 3. Authority and roles

| Role | Authority and responsibility |
|---|---|
| User | Approves planning/setup changes, resolves contract changes, starts/stops QA, performs final merge into `main` |
| Coordinator | Schedules approved feature work, manages PR lifecycle and integration, dispatches permitted corrective work |
| Host launcher | Deterministic claims/state, local clone/session lifecycle, result collection, GitHub PR operations and serialized gated integration |
| Slice Orchestrator | Owns one slice, delegates implementation/verification/review, manages bounded repairs, reports or escalates |
| Builder | Implements with TDD, writes committed tests, performs scoped refactoring, creates clean commits |
| Tester | Independently runs agreed checks and assesses acceptance coverage; no product-code or committed-test edits |
| Reviewer | Fresh-session, read-only review against requirements and applicable coding/architecture standards |
| Explore | On-demand local codebase discovery within the caller's execution boundary |
| Research | On-demand external evidence, citations and explicit uncertainties |
| Recaper | Optional finished-feature walkthrough; no execution gate or code changes |

Agent prompts are thin contracts around skills, not duplicated procedural loops.

- Use an adapted `implement-spec` as the Coordinator's starting method. Validate
  actual local session/subagent tool directories rather than relying on prompts.
- The Coordinator may read approved planning/results and use the narrow launcher
  interface; it cannot edit application code or execute arbitrary host commands.
- Workers do not manage PRs or receive PR-management credentials through the
  workflow. The launcher creates/updates PRs from results; the Coordinator manages
  their lifecycle. Shared-host credential exposure is not sandbox-contained.
- Each Orchestrator stops after its one slice. It never claims another on its own.
- Remove the mandatory post-verification Refactorer and Cleaner phases. Refactoring
  and commits belong to Builder; artifact collection/cleanup belongs to the launcher.
  An explicitly targeted Refactorer may remain optional.
- Remove Tester's scaffold mode. Missing test coverage returns to Builder; Tester
  does not weaken tests or own the repair loop.
- Normal handoff includes a short structural summary. Recaper defaults to the
  finished feature, not whichever slice archive is newest.

### Execution autonomy

Agents may inspect code, resolve implementation details and revise a mistaken
technical approach while preserving approved behavior, scope and constraints.
Document deviations and verify the result.

Product ambiguity, conflicting requirements, and changes to scope, architecture,
security boundaries or dependencies affecting other slices require a recommendation
and user approval. Do not silently rewrite acceptance criteria. Challenge incorrect
contracts rather than blindly implement them.

## 4. Dispatch, state and concurrency

- One active Coordinator per feature, enforced host-side. Different independent
  features may have concurrent Coordinators.
- Default launch: at most three dependency-ready slices in a bounded batch. Do not
  refill it with newly unblocked work. Support explicit single-slice mode.
- Whole-feature mode is explicit: continue with newly ready work within the
  approved graph and limits. Block affected dependency chains, not unrelated work.
- Per-feature worker concurrency defaults to three, configurable per project.
- Initial host-wide worker cap: three, including reconciliation/correction workers.
- Separate host-wide integration-check cap: three. Integration stays serialized
  per feature. These pools allow up to six automatic environments in total.
- User-started QA environments are outside both pools. Their load remains visible.
- Use launcher-owned execution state files and OS-backed locks, not SQLite for v1.
  Workers have no authorized direct state/lock writes. Validate role permissions
  and document that a shared host identity is not OS-level containment.
- Enforce exclusive claims, idempotent launch requests, atomic state updates,
  checkpoints and deliberate recovery. Markdown is not a locking mechanism.
- Runtime state is authoritative for operational status. Human-readable backlog
  status, if provided, is a derived view, not a second writable authority.
- If no eligible work is available, report why rather than duplicate work or bypass
  dependencies. Do not mistake temporarily waiting for authorized active work for
  permission to claim different or additional work.

## 5. Launch and result contract

The validated launch request identifies feature, slice and unique run; approved
spec/ticket versions; exact starting feature commit and branch; approved project
profile; local agent/skill bundle snapshot; limits; and approved credential references.

Claim before preparation. Make the actual handoff artifacts accessible to the
slice's local sessions; inaccessible paths or incomplete summaries are insufficient.

Results identify run/slice, branch, start/final commit anchors and outcome:
ready-for-integration, blocked or failed, with interrupted state represented in
host recovery records. Include applicable acceptance coverage, executed checks,
independent review, evidence/log references, summary, deviations, risks/escalation
questions and PR references when available.

Evidence must describe the exact final commit. Missing checks/review are not
passes. A worker report is evidence for the host gate, not unconditional merge
authority. Track the complete slice range, not only Builder's first commit.

## 6. Trusted local execution; sandbox deferred

- Use the narrow deterministic host launcher and independent local clones; no
  required Docker/Compose worker, sandbox framework or Sandcastle dependency.
- Each slice has its own directory, Git metadata and distinct branch. No Git
  worktrees or shared-clone alternates. Record the exact verified feature baseline.
- Orchestrator/subagents/tools must operate in their assigned clone. Validate real
  tool directory binding and session ownership on the actual OpenCode V2 release.
- Before running the implementation loop, qualify basic stopping of owned
  parent/subagent sessions and tracked commands without disrupting the shared
  OpenCode service or unrelated work. Uncertain stopping prevents progression;
  comprehensive crash supervision and recovery remain a later milestone.
- Run approved setup/test/build and integration commands locally on trusted projects.
  Integration uses a disposable independent candidate checkout. Launcher Git
  operations must avoid accidental repository hook/config execution.
- Project-specific services and development access still require approved setup.
  Existing Compose app dependencies may be used without sandboxing agents. Coordinate
  shared ports/services/paths or serialize work that cannot safely coexist.
- No production credentials/data or deployment. Use approved development/test/model
  access, secret references and redacted evidence, never secret values in requirements.
- Review effective tool/MCP/configuration access and enforce available role controls.
  Before the implementation loop, verify effective role/tool configuration against
  approved inputs, including relevant inherited configuration, and record its
  non-secret identity. Unapproved overrides or unverifiable configuration hold the
  run; copying an approved prompt/skill bundle is not sufficient proof.
  Do not claim that separate clones or role permissions prevent access to host files,
  ambient credentials, Docker, networks, other clones or processes.
- Runtime/concurrency/repair bounds remain. Hard container CPU/memory/PID/disk quotas,
  firewall/proxy restrictions and credential-isolation qualification are deferred,
  not silently weakened sandbox gates or passing workflow evidence.
- Preserve existing sandbox work/evidence and host configuration. Rethink and plan
  its separate project after workflow implementation; do not design it now.

## 7. Verification and integration

### Slice gate

- Account for every applicable criterion with evidence; an unresolved required
  criterion prevents integration.
- Pass required project tests, lint/type checks and build where applicable.
- Complete independent review with no unresolved blocking findings.
- Review blockers include unmet criteria, correctness/security defects, violated
  explicit constraints/required standards, or missing necessary verification.
- Preferences and optional improvements are advisory unless required by policy.
  Blocking findings identify a violated requirement/standard or concrete risk.
- Mutations invalidate relevant evidence and require renewed checks/review.

### Verify before publishing

Prepare the combined integration candidate in a disposable checkout, retaining it
with a local Git reference. No published candidate branch or extra PR is required.
Verify that exact combined commit before advancing the feature branch. Preserve
failed candidates/diagnostics without changing the last verified feature head.

Serialize publication and validate the expected feature head. Do not publish a
different result if the branch moved during verification. A clean merge or passing
individual slices does not establish that the combination passes.

### Conflict and contract disagreement

Hold affected integration and new consumer dispatch. Already-running affected
workers may finish within their budgets, but outputs remain provisional. Unrelated
work may continue within its existing authorization.

For implementation-only conflicts preserving every approved contract, the
Coordinator may dispatch **one reconciliation run per affected conflict group**,
beyond the original batch. Use normal slice time/repair limits. Recheck/review the
combined result. Further failure or required contract changes escalate; no recursive
reconciliation or relabeling groups to reset limits.

If the contract itself is wrong, escalate the proposed correction for user
approval before proceeding on the changed basis.

## 8. Budgets, interruption and recovery

| Limit | Initial default |
|---|---|
| Slice runtime | 60 minutes, including setup, implementation, checks and repairs |
| Slice inactivity | 10 minutes without progress, subject to tracked-command rule |
| Repair budget | Two corrective implementation passes after initial implementation |
| Integration-check runtime | 30 minutes, including preparation and verification |

Time budgets are configurable per project. Capacity waiting does not consume
slice/integration runtime; timers start at environment preparation.

- Use one shared repair budget across checks and review. Multiple failures may be
  addressed in one pass. Rechecking, stage changes and fresh subagents do not reset
  it. Initial expected TDD failures are not repair attempts.
- Escalate earlier for repeated failure without meaningful progress. Preserve
  tests across repairs; do not shrink coverage to make checks pass.
- Quiet tracked setup/test/build commands may run until their command deadline.
  Absence of text alone is not inactivity; service heartbeats alone are not progress.
  The total runtime cap still applies. Dead/expired commands cannot suppress idle
  detection indefinitely.
- Invalid requests/setup failures report diagnostics, not completion. Failed or
  timed-out verification never advances the feature head.
- On Coordinator crash, supervise existing workers to completion within their
  budgets and collect results; hold new dispatch and integration for deliberate
  recovery.
- On worker interruption, preserve checkout and evidence. Confirm the old worker
  is stopped before reassignment. Recover in a fresh session using durable inputs
  and checkpoints; retain consumed time and repairs. Exhausted budgets need user
  authorization for extensions. Reverify the recovered final state.
- Explicit stop-feature halts dispatch/integration and stops active automatic
  sessions and tracked commands, preserving state. It does not roll back already-published verified
  integrations or stop user-started QA unless separately requested.

Workflow-level monetary caps and cost accounting are **out of scope for v1**; the
user relies on an existing provider/account limit. Keep available host-load
visibility for tuning, without claiming hard resource containment or unvalidated
billing guarantees.

## 9. Project onboarding and readiness

Separate one-time routine installation from project onboarding. Project setup is
a reusable skill for any suitably authorized interactive agent, not a mandatory
Setup agent. Skill loading never expands permissions.

1. Discover existing conventions, domain docs, toolchain, setup/check commands,
   services, credential needs and GitHub/merge settings.
2. Propose changes, an approved profile and a validation plan. Include required
    commands, applicable criteria, local runtime services/access, credential
    references, concurrency/command limits and QA start/stop behavior.
3. Obtain user approval **before** scaffolding, configuration edits, dependency
   installation, provisioning or other mutating setup. Apply only approved changes;
   additional scope returns for approval. Do not overwrite existing credentials.
4. Validate a disposable independent local clone: approved setup, directory-bound
    named agents/tools, baseline checks, runtime health and QA access, then cleanup.
5. Report ready for the tested revision/profile or report gaps and proposed work.
   Relevant changes require reassessment; readiness is not a permanent blanket pass.

Required baseline checks must be green unless the user explicitly approves a
narrow exception. Reproduce/document pre-existing unrelated failures; exceptions
remain visible, never reported as passes, and do not cover new/feature-relevant
failures. Missing checks require assessment, not silent weakening of the gate.

Existing projects reuse their commands/services/docs rather than replacing the
stack. New projects require agreed stack/architecture and approved bootstrap work
with explicit checks for the feedback infrastructure it creates; nonexistent
tests cannot be an impossible prerequisite for creating that infrastructure.

Respect each project's merge conventions. Propose GitHub required checks and
protections through approved setup. State enforcement limits for manual/admin
actions; do not pretend the launcher controls every possible manual merge.

## 10. Feature completion, QA and main

- Preserve slice PRs for traceability; routine human slice approval is not required.
- Final review compares the integrated feature with the **full spec**, not only
  tickets. A decomposition can omit requirements even if every slice passes.
- If full-spec review finds omissions, the Coordinator may dispatch **one bounded
  corrective slice per feature**, beyond the original batch, under normal time/
  repair limits and unchanged contracts. Not one new slice per finding. Further
  failure or contract change escalates. Reverify/review the corrected feature.
- Keep active slice work on its recorded feature baseline, not continuously updated
  from other features' changes to `main`. Consumers may start from newer verified
  commits within their own feature as prerequisites integrate.
- Before final QA, synchronize with latest `main` and repeat integration checks
  and full-spec review, using verify-before-publish.
- Handoff: final feature PR, slice PRs, exact verified commit/main baseline,
  acceptance coverage/check/review evidence, deviations/risks, short structural
  summary, QA checklist and a way to start the integrated feature's QA environment.
- **Do not automatically leave a preview running.** QA uses explicit start/status/
  stop actions and the identified verified state, including suitable CLI/API/demo
  environments for non-browser projects.
- User-started QA remains running until the user stops it. No automatic expiry or
  agent shutdown by default; available host-load visibility remains.
- Approval applies to the exact reviewed state/main baseline. If `main` advances
  during QA or before merge, hold the merge, synchronize/reverify, refresh the QA
  handoff/preview state and request renewed approval with a short change summary.
- The user performs the final merge into `main`. Agents stop at review-ready
  handoff; they do not perform final main merges or deploy.

## 11. Skills, documentation and retention

Initial skill scope: `grill-with-docs`, `to-spec`, `to-tickets`, `tdd`, `code-review`,
`handoff`, `research`, `writing-for-agents`, `implement-spec`, and necessary
setup/transitive dependencies. Do not bulk-install the entire upstream collection.

Skills are locally owned/adaptable copies with origin notes, not submodules,
upstream runtime dependencies or managed auto-update links. Adapt unsafe/conflicting
instructions. Snapshot the **local** agent/skill bundle when a feature starts and
record its identity per run/recovery. Make it available to the local role sessions;
no worker-image packaging is required. Later edits apply to future features, not
silently to running work. This is not an upstream source-version commitment.

Retain the feature spec through execution/QA. Archive superseded brainstorming/
alignment rather than delete it on planning approval. Current-document references
are explicit; archives are historical, not competing execution authority.

Stop owned automatic worker/check sessions and commands after safe result collection. Keep
successful checkouts until feature acceptance; then remove generated environments.
Preserve failed/interrupted checkouts until explicit cleanup. Retain specs,
summaries, PR references and verification evidence. Automatic cleanup must not
touch user-started QA or silently delete retained evidence under storage pressure.

## 12. Implementation planning and validation obligations

The implementation plan must resolve reversible engineering details without
reopening the agreed product contracts: profile/ticket/state schemas and locations,
validated launcher interface, locking/checkpoint algorithms, artifact/commit
transfer, GitHub mechanics, local-bundle packaging, concrete command/progress
signals, shared local runtime coordination and cleanup. Choose a narrow design;
do not expand v1 into a general scheduler/sandbox platform or future-backend framework.

Validate against disposable fixtures, including:

- Two independent slices and a contract-owning slice with a blocked consumer.
- Real local OpenCode/subagent directory binding and independent clone Git state;
  these prove routing/work separation, not host security isolation.
- Duplicate launch/claim prevention, one Coordinator per feature and both capacity
  pools, with queued time excluded from runtime budgets.
- Required-criterion/check/review failures and missing evidence preventing admission.
- Failed combined candidates leaving the feature head unchanged.
- Technical reconciliation, contract-change escalation and non-recursive budgets.
- Full-spec omission correction without unbounded additional dispatch.
- Crashes/interruptions at execution and integration checkpoints, preserved partial
  work, deliberate recovery and no duplicate live worker.
- Cancellation, stale main/approval handling and user-owned QA start/stop/cleanup.
- Approved local command/access handling, role permission restrictions, evidence
  redaction and documented shared-host exposure; sandbox restrictions are deferred.

Address every S1–S14 finding explicitly in the plan/test evidence: criteria
visibility, post-mutation verification, one runtime authority, complete recovery,
state ownership, complete final commit ranges, stall detection, least-privilege
permissions, test preservation, scope containment, bounded execution, role-based
flow rather than inconsistent phases, correct/shared diagram guidance, and no
Tester-owned repair loop. Do not introduce an unbounded loop under a new name.
