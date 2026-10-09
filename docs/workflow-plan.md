# Feature delivery workflow plan

**Direction approved 2026-10-06. Runtime assets adapted and trusted-local delivery
trials verified 2026-10-08.** Evidence, limitations and retrospective are recorded
in [workflow-adoption.md](workflow-adoption.md). This plan replaces the manual S0
and custom-launcher direction.
Historical revisions of the superseded workflow remain available in Git.
Product decisions are summarized in [alignment.md](alignment.md); workflow terms
are defined in [CONTEXT.md](CONTEXT.md).

The objective is a short path from an approved outcome to a QA-ready feature:
one planning context, one feature kickoff, autonomous dependency-aware execution,
one final feature gate and human control of the merge to `main`.

## 1. Operating principles

- The **feature** is the normal authorization and review unit. A ticket is an
  internal execution unit, not a routine human approval gate.
- One explicit feature kickoff authorizes the complete approved ticket graph.
  Newly unblocked tickets may start without another prompt.
- Use small, composable skills as the workflow. Agent prompts define authority and
  responsibility; they do not duplicate the full procedure.
- Use one integration branch and separate Git worktrees for concurrent tickets.
  Worktrees separate working files and Git state; they are not security sandboxes.
- Prefer Git, tracker records and preserved worktrees as recoverable state. Do not
  build a launcher, ledger or scheduler before observed failures justify one.
- Run trusted local development only. No production data/access, deployment or
  security-isolation claim is authorized.
- The user owns final QA and the merge into `main`.

## 2. One-time project setup

Adapt the upstream `setup-matt-pocock-skills` pattern once per repository:

1. Record the issue tracker. Local Markdown is the default; GitHub or another
   tracker may be selected per project.
2. Record the domain-document layout and, where applicable, tracker labels.
3. Discover the project's existing setup, test, lint, type-check and build commands.
4. Record branch/PR conventions, development-only access, shared services and QA
   instructions. Do not write secret values into workflow documents.
5. Confirm that ordinary local implementation commands and baseline checks work.

Normal feature work reads this configuration and does not ask for it again. Missing
feedback loops or setup requirements become explicit setup work; they are not
silently waived to start a feature.

## 3. Two delivery paths

### Fast path — one bounded change

Use the fast path when the request:

- fits in one fresh implementation context;
- has clear, testable acceptance;
- does not change an unapproved shared contract, architecture or security boundary;
- has no dependency graph worth manufacturing.

The request plus one concise acceptance confirmation authorizes one Implementer to
use TDD, run relevant checks, commit the change, obtain final review and hand back
the result. Do not create a ceremonial feature spec or ticket graph.

### Feature path — a ticket graph

Keep planning in one primary session where practical:

1. Brainstorm only when exploration is useful.
2. Use `grill-with-docs` to resolve real ambiguity and sharpen domain language.
3. Use `to-spec` to synthesize the discussion; do not start a second interview.
4. Use `to-tickets` to propose tracer-bullet tickets and blocking edges.
5. The user approves the feature spec and ticket graph.
6. A later explicit `implement-spec <spec>` instruction authorizes the whole graph.

The approved spec describes the destination. Tickets describe the journey. They
may reference the spec rather than duplicating it, but every Implementer must be
able to read both the ticket and its applicable feature requirements.

## 4. Feature execution

The Coordinator owns one feature from kickoff to QA-ready handoff:

1. Confirm the approved spec, ticket graph, project profile and starting baseline.
2. Create a feature integration branch and worktree. Leave the user's normal
   checkout and `main` unchanged.
3. Determine the **frontier**: every incomplete ticket whose blockers are complete.
4. Create a branch and worktree for each dispatched frontier ticket and start a
   direct Implementer child session there. Concurrency is project-configurable.
5. Move each child session's OpenCode Location to its assigned worktree before any
   project operation. The child confirms its Location, Git root, branch and HEAD.
   A path written only in a prompt is not sufficient routing evidence.
6. Each Implementer uses `tdd`, implements only its ticket, runs relevant checks,
   reviews its diff and creates focused commits. It reports the exact final commit,
   checks, deviations and blockers.
7. A Merger integrates completed ticket work into the feature branch one ticket at
   a time and runs the applicable integration checks. Implementation-only conflicts
   may be resolved while preserving every approved contract. Product or contract
   disagreement is escalated instead.
8. Close or update the ticket according to the configured tracker. Recompute the
   frontier and dispatch newly ready work until the graph is complete or blocked.
9. Automatically remove clean, successfully integrated generated ticket worktrees.
   Preserve failed, interrupted or ambiguous worktrees for diagnosis and recovery.

Different features may run concurrently. Each has a distinct integration branch,
worktree and Coordinator. Shared ports, databases, generated paths or scarce host
resources are project-runtime concerns and may require namespacing or serialization.

## 5. Verification and repair

Routine tickets rely on Implementer TDD plus Merger integration checks. Do not run
a serial independent Tester and Reviewer gate for every ticket by default.

A ticket explicitly marked high-risk may require independent ticket-level review.
The planning package should identify this when risk is already known; the
Coordinator may also recommend it when implementation reveals concrete risk.

After all tickets are integrated:

1. An independent Tester runs the agreed project checks against the exact feature
   commit and accounts for the full spec's acceptance criteria.
2. A fresh Reviewer inspects the complete baseline-to-feature change against the
   full spec and applicable standards. Give the Reviewer read-only Git inspection
   rather than copying a diff through the Coordinator.
3. Tester and Reviewer may run concurrently when their commands and workspaces do
   not interfere.
4. Blocking findings go to one focused repair Implementer. Use at most two repair
   passes by default; rerun affected checks and fresh final review after mutation.
5. Missing checks, missing review or unresolved blocking findings are not passes.

The final gate is feature-level because a correct set of tickets can still omit a
spec requirement or fail when combined.

## 6. Publication and human QA

- Do not create slice PRs by default. Tickets, branches and commits retain internal
  traceability without adding remote lifecycle work.
- When the project uses hosted review, create one feature PR from the verified
  integration branch. Otherwise report the local branch and exact commit.
- Include the baseline, final commit, acceptance coverage, check/review results,
  deviations, risks and a short QA checklist.
- Provide a project-appropriate way to inspect or run the feature. Do not leave a
  persistent preview running unless requested or authorized by project policy.
- The user performs final QA and merges into `main`. Agents do not deploy.

## 7. Authorization and escalation

The feature kickoff authorizes routine local delivery inside generated worktrees:
edits, project checks, dependency-ready dispatch, local branches, commits, merges
into the feature branch and safe cleanup of successfully integrated generated
worktrees. OpenCode permissions should allow these normal operations without
repeated prompts.

Pause and ask the user only for:

- unclear or conflicting product intent;
- a change to approved scope, shared contracts, architecture or security boundaries;
- missing credentials, provisioning or a genuinely human-only action;
- production/deployment access;
- destructive work outside owned generated worktrees;
- remote publication not covered by project setup;
- exhausted repair attempts or unresolved blocking verification;
- final QA and merge into `main`.

Use native OpenCode V2 `permissions:` rules. Retain explicit protection for secrets,
external directories, destructive commands and `main`; do not put all ordinary
shell work behind `ask` after the feature has already been authorized.

## 8. State, interruption and recovery

There is no custom Host launcher or runtime ledger in the initial workflow.

- One Coordinator owns a feature run.
- The configured tracker records the approved graph and completion state.
- Git branches and commits record integrated work.
- Worktrees preserve active or interrupted changes.
- OpenCode sessions provide live execution identity while available.

After interruption, resume by reconciling the tracker, integration branch, ticket
branches/worktrees and available sessions before dispatching anything new. Never
discard uncertain work or start a duplicate Implementer for the same ticket. Add
deterministic state tooling only in response to a demonstrated recurring failure.

## 9. Roles and skill ownership

| Role | Responsibility |
| --- | --- |
| User | Approves the planning package, starts feature execution, resolves contract changes, performs QA and merges to `main` |
| Coordinator | Owns one feature graph, worktree dispatch, frontier scheduling, integration, final gate and handoff |
| Implementer | Owns one ticket or fast-path change, including TDD, checks and focused commits |
| Merger | Integrates completed ticket branches and verifies the resulting feature state |
| Tester | Independently verifies the completed feature and acceptance coverage |
| Reviewer | Fresh, read-only review of the completed feature against the full spec and standards |
| Explore / Research | Optional focused discovery, returning concise reusable findings |

Vendor a reviewed snapshot of the required Matt Pocock skills and record its exact
upstream commit. Initial set: `setup-matt-pocock-skills`, `grill-with-docs` and its
dependencies, `to-spec`, `to-tickets`, `implement`, `implement-spec`, `tdd` and
`code-review`. Make only documented OpenCode-specific adaptations. Do not silently
auto-update skills during a feature.

## 10. Adoption sequence

1. Vendor and document the selected skill snapshot.
2. Replace mandatory Brainstormer/Aligner/Planner handoffs with one skill-driven
   planning agent; specialist agents may remain optional.
3. Replace the one-slice Orchestrator hierarchy with the flattened Coordinator,
   Implementer and Merger roles. Adapt Tester and Reviewer to the feature gate.
4. Replace legacy singular `permission:` definitions with verified OpenCode V2
   `permissions:` rules matching the authorization contract above.
5. Prove routing with two parallel no-op child sessions in separate worktrees. Each
   must report the correct Location, Git root, branch and HEAD without modifying the
   other worktree.
6. Trial the fast path on one bounded trusted-local change.
7. Trial the feature path on a small two- or three-ticket graph, including at least
   one dependency edge and final full-feature verification.
8. Run a retrospective. Fix observed friction with the smallest change; do not
   revive launcher/ledger infrastructure speculatively.

Adoption succeeds when one approved kickoff reaches a QA-ready feature without
routine user intervention; concurrent agents remain in their assigned worktrees;
dependencies and integration are correct; normal commands do not repeatedly ask;
final independent verification covers the full spec; interrupted work is recoverable;
and `main`, production and deployment remain human-controlled.
