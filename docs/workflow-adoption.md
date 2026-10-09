# Lightweight feature delivery — adoption

Implements the approved direction in [workflow-plan.md](workflow-plan.md) and
[alignment.md](alignment.md). Superseded S0/launcher revisions remain in Git;
additional historical drafts stay local and untracked.

## Installed assets

- Reviewed Matt Pocock skill snapshot pinned to
  `b0618bc436ad893b3c5e84e55fba86586d34a404`, with license, original file hashes,
  dependency closure and documented OpenCode adaptations. See
  [provenance](../common/opencode/.config/opencode/workflow/UPSTREAM.md).
- One Planner context composes optional brainstorming, domain grilling, spec
  synthesis and dependency-aware ticketing. Approval is separate from kickoff.
- Stable `orchestrator` ID now means feature Coordinator; `builder` means
  Implementer. New `merger` integrates exact ticket commits serially. Tester and
  fresh read-only Reviewer gate the complete feature rather than every ticket.
- Native V2 agent permissions allow ordinary trusted-local delivery while retaining
  secret/external-directory/destructive-command/remote/`main` guardrails. They are
  best-effort controls, **not a sandbox or a branch-aware security guarantee**.
- Skills own verified child Location routing, dependency-ready dispatch, bounded
  repairs, safe generated-worktree cleanup, interruption recovery and human handoff.
  No launcher, ledger, mandatory cleanup/refactoring phase or per-ticket PR lifecycle.

Existing optional specialist IDs are retained. Model preferences are preserved and
reasoning selection uses native `#variant` references rather than legacy fields.
MCP/provider/client settings and unrelated skills are not replaced.

## Use

Stow/restow the package if it is not already linked, then reload the installed
configuration (OpenCode V2.0.22 was used for validation):

```sh
stow -R -t ~ -d common opencode
opencode reload
```

Configure a project once with `/setup-matt-pocock-skills`. This records the tracker
(local Markdown by default), domain layout, runnable feedback loops, runtime limits,
branch/publication policy and human QA instructions under `docs/agents/`.
Missing feedback loops are setup blockers, not silently skipped checks.

- Bounded work: `/implement <request>`; confirm concise acceptance once.
- Feature planning: optionally `/grill-with-docs`, then `/to-spec` and `/to-tickets`
  in the same Planner session. Approve the spec and graph.
- Feature execution: `/implement-spec <spec>` explicitly authorizes the whole graph.
  Routine local work and newly unblocked tickets do not need repeated user prompts.
- Final result: independently checked/reviewed exact feature commit, one authorized
  feature PR or a local branch, plus a QA checklist. The user owns QA/`main` merge.

The generated feature worktree remains available for QA. Failed/dirty/ambiguous
worktrees are preserved. No persistent preview, production access or deployment is
authorized by default. Projects may narrowly configure approved hosted publication;
permission denials are honored rather than bypassed.

## Verification record — 2026-10-08

`python3 -m unittest discover -s common/opencode/.config/opencode/tests -v`:
**13 checks pass**. The suite verifies
asset/dependency links and original supporting-file hashes, command context/routing,
native agent discovery, thin/flat dispatch permissions, routine-command approval,
read-only review, foreground/completion lifecycle clauses and protected command/path
precedence (including feature names containing `main`). Runtime checks require
OpenCode and this package to be stowed. They evaluate loaded ordered rules; they
do not prove shell containment or every scanner interpretation.

The existing service cached old definitions until `opencode reload`; a fresh
discovery check now confirms the new role prompts. No service restart was needed.

### Parallel no-op routing proof — pass

Disposable fixture baseline: `598fbef379ef248faff2b07c1c537b0c0299339c`.
Both children moved their **own** Location first, independently confirmed `pwd`,
Git root, branch, HEAD and clean status, and read `README.md` via a relative path.
Neither modified files/Git or the other worktree.

| Child session | Assigned Location | Branch | Result |
| --- | --- | --- | --- |
| `ses_ee3cd0876ffehI9gbTjO2BuJ7i` | `/tmp/opencode/feature-workflow-routing-20261008/ticket-a` | `ticket/routing-a` | pass |
| `ses_ee3cd0873ffeHZIfDvQylDJZJK` | `/tmp/opencode/feature-workflow-routing-20261008/ticket-b` | `ticket/routing-b` | pass |

### Fast path — passed after permission correction

Disposable Python fixture baseline: `62225aa8ecc3b2f5a7a6f613f8fea1da104ca492`.
Final commit: `7b36df999e7cd3b54126a40e23b69465d6540463` on `feature/trial-fast`.
One Implementer added `greeting.greet`, with public-function tests for `Ada` and an
empty name. Independent Tester passed all three tests on that exact unchanged SHA.
Fresh final Reviewer `ses_ee3baf98bffea04Hw0uCd0fqZq` used separate read-only Git
calls, including `git ls-files`, and passed both axes with zero findings.

Feature/verification worktrees are preserved for QA. Exact references, role routing,
acceptance and commands are in
`/tmp/opencode/feature-workflow-trials-20261008/trees/greet-fast-20261008/HANDOFF-greet-fast.md`.
No spec/graph was manufactured for this fast-path request; unrelated graph planning
inputs were preserved. Nothing was published, deployed or merged into `main`.

### Dependency graph — verified repetition completed

The two-ticket arithmetic graph (`01 -> 02`) reached a tested/reviewed local
handoff at `7cd5a66b421968f45e40f46b756b1c6e07380b31` on `feature/trial-graph`.
Four tests and byte-exact positive/negative CLI checks passed; all three feature
acceptance criteria were covered. Both review axes passed with zero findings.
Its tracker records exact ticket/integration commits. Evidence is in
`/tmp/opencode/feature-workflow-trials-20261008/trees/trial-graph-integration/FINAL-HANDOFF.md`.

This first run required CLI continuation and integrated ticket 02 before its
completion notice arrived. It therefore demonstrates functional delivery, **not**
full adherence to the corrected lifecycle contract. Earlier trial worktrees remain
preserved for diagnosis/inspection.

A distinct `feature/trial-graph-final-proof` repetition completed at
`e70eebe61aa8a3eed9fdebc83d9b922e4f0e7f40`. Every child was foreground and returned
its result before integration or cleanup. Ticket 02 started only after checked
integration of 01; mergers serialized the work without conflicts. Tester passed
all three acceptance criteria and the identity regression: six tests and byte-exact
CLI results at that unchanged final commit. Clean, completed, integrated ticket and
repair worktrees were removed non-force after ancestry checks; branches and feature/
verification worktrees were retained. Earlier trial worktrees were not touched.

One focused repair corrected tracker dispatch provenance. Final review initially
blocked on missing original TDD evidence. Native Builder session records were then
recovered through OpenCode's API; both show failing tests **before** production
patches and passing tests afterward. Fresh Reviewer
`ses_ee3a8b643ffeEZ9NHcrvHvhBbz` inspected those original records and the complete
baseline-to-final diff, resolving the blocker without a waiver or rewritten history.
The existing Tester pass remains valid because the feature SHA did not change.

Original evidence sessions: `ses_ee3babf0dffe6XxX2CeuBHrtuV` (01) and
`ses_ee3b86594ffeyDI8cI1xFU4PLs` (02). Exports are preserved at
`/tmp/opencode/<session-id>-tdd-evidence.json`. The final handoff is
`/tmp/opencode/feature-workflow-trials-20261008/trees/graph-final-proof/FINAL-HANDOFF.md`.
No blocking findings remain. Nonblocking advice: finish the first red/green cycle
before adding more test cases, rather than batching cases for the same small seam.

The repetition reached verified behavior, dependency scheduling, completion-aware
integration/cleanup and a resolved full-feature gate from one kickoff. It still
needed author-session intervention to retrieve omitted process evidence. That
friction is documented below; the contract now requires original-record recovery
before unnecessary repair/waiver requests. A subsequent real feature should confirm
that this correction removes the remaining diagnostic intervention. Hosted
publication, production/deployment and security containment were not trialed or
authorized. Nothing was merged into `main`.

### Asset review and retrospective

Fresh read-only WIP review `ses_ee3bb2394ffeBsWkwoKUprm320` covered all owned
tracked/untracked assets against the approved plan: no blockers, one advisory to
protect lifecycle clauses with regression assertions. Those assertions are now
included in the 13-check suite. This review is not a committed feature gate:
at the time, implementation files remained uncommitted in the user's checkout,
with unrelated pre-existing work preserved.

Follow-up full WIP review `ses_ee3b1f509ffeSWjhCKcUZZHOUE` found no blockers.
Its optional additional permission-case coverage remains advisory, not a delivery
gate. No unrelated user work was included in either asset review.

Repository cleanup on 2026-10-09 moved the regression suite alongside the OpenCode
configuration, updated its run instructions and kept superseded drafts untracked.
All 13 checks passed again from the repository root after the move.

Observed friction was addressed with small changes rather than runtime machinery:

1. Do not repeat a broad external-directory ask after OpenCode's managed exceptions;
   it blocked required skill references. Preserve the native managed-directory rules.
2. Use foreground children for noninteractive `opencode run`; a waiting summary
   ended the CLI invocation. Background dispatch requires demonstrated continuation.
3. Wait for child completion/results, not merely a clean worktree or visible commit,
   before integration or cleanup. Never bypass a denied read via shell or another path.
4. Permit `git ls-files` narrowly for Reviewer discovery, retaining shell mutation
   denies. Keep read-only inspections as separate calls.
5. Treat the explicitly supplied spec/request as authoritative; other feature plans
   are neither this feature's acceptance nor disposable stale notes.
6. Match protected push refs as tokens/destinations, not `*main*` substrings that
   incorrectly block `feature/domain-model` or `feature/main-menu`. Unapproved feature
   publication still asks; this remains best-effort protection, not shell containment.
7. Preserve and retrieve original Builder tool records for process-review findings.
   A missing handoff reference does not mean the evidence is unavailable. Verify
   native chronology before reconstructing tests, consuming a repair pass or asking
   the user to waive a requirement; don't turn missing pointers into invented blockers.
