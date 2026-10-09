# OpenCode local execution contract

Shared by `implement-spec` and `implement`. This is a prompt-driven workflow, not
a launcher, scheduler, ledger or sandbox. Roles read project configuration from
`docs/agents/{project,issue-tracker,domain}.md` (or explicit project instructions).
Missing setup/checks become setup work; never silently waive them.

Read required supporting files with the read tool. If a read or another operation
is denied, stop and report it; do not retry via shell, another tool/path or copied
contents to bypass the denial. The user may authorize a narrow policy correction.

## Routing every child

Supply the exact absolute assigned worktree path, branch or detached-HEAD status,
expected start SHA, baseline, requirements, check commands and scoped authority.
The child's **first operation** is to move its own OpenCode Location:

```js
return await tools.opencode.session_move({ directory: "<assigned-absolute-worktree>" });
```

Use the `execute` tool for this call. Without `sessionID`, it moves the child,
not its parent. Before reading or editing project files, the child reports the
returned Location and runs separate `pwd`, `git rev-parse --show-toplevel`,
`git branch --show-current`, `git rev-parse HEAD` and `git status --short` calls
with that worktree as `workdir`. Compare all values to the assignment. A prompt
path or `git -C` is not routing evidence. If Location movement is unavailable,
denied or wrong, stop; no reset, original-checkout fallback or broad permissions.

The Coordinator may route an existing **idle** session by exact `sessionID` before
continuing it, but must still obtain the child's own identity confirmation.
Children receive their own permissions, not the parent's. No nested delivery agents.

Background dispatch is preferred when the parent interface will receive completion
notifications and resume execution. For a noninteractive `opencode run` invocation,
use foreground children unless durable continuation has been demonstrated; returning
a waiting summary ends that CLI invocation and is not a QA-ready handoff. Do not
start a duplicate worker merely because the original CLI disconnected.

## Final verification

1. Pin the completed integration SHA. No implementation or integration may mutate
   it while the gate is running. Give `tester` the full spec/acceptance and all
   agreed commands; give a fresh `reviewer` the full spec, standards, exact baseline
   and final SHA. Both move their own Location and confirm Git identity first.
2. Tester accounts for every criterion and runs agreed checks. Reviewer loads
   `code-review` and inspects the complete two-dot `git diff <baseline> <final>`
   directly using read-only Git, reporting spec and standards axes independently.
   No copied/truncated diff is a substitute. A missing check, review, criterion or
   unresolved blocker is not a pass; advisory preferences do not force repair.
   For process findings such as TDD chronology, give the Reviewer the Implementer's
   original check results and session/message references. If a report omits evidence,
   retrieve the assigned child's original tool records through the documented
   OpenCode API before dispatching repair or asking for a waiver. Preserve original
   commands, outputs and ordering; don't fabricate history or confuse a post-hoc
   reconstruction with a contemporaneous run. Runtime transcripts need not be
   committed to product history. A missing pointer is not proof that no record exists.
3. They may run concurrently only with non-interfering workspaces/commands. When
   checks write tracked/generated files, use a separate generated verification
   worktree at the exact final commit for Tester; keep Reviewer on the immutable
   feature worktree. Shared services must still follow project runtime policy.
4. Blocking findings go to **one** focused repair `builder` in a generated repair
   branch/worktree based on the exact final SHA. At most two repair passes after
   initial implementation by default. Merger integrates the exact repair and runs
   integration checks. Rerun affected and all required final checks plus a fresh
   review on the new complete baseline-to-final range. Never reuse stale results.
   Exhausted repairs or contract/scope/security changes require user escalation.

## Publication and handoff

- On pass, verify integration HEAD still equals the tested/reviewed SHA. If hosted
  publication is explicitly enabled by setup, push only the feature branch and
  create/update **one** feature PR with spec/ticket references. Otherwise report
  the local branch and SHA. Permission prompts still apply: denied publication is
  a reported blocker, not permission to broaden rules. No automatic `main` merge.
- Report baseline, final SHA, acceptance coverage, commands/outcomes, independent
  review, deviations, risks and a short project-appropriate QA checklist. Provide
  inspect/run instructions; do not leave a persistent preview running unless
  requested or pre-authorized. User performs QA and merges into `main`.
- Keep the feature worktree for QA. Only clean, owned, successfully verified
  generated ticket/repair/verification worktrees with completed sessions may be
  safely removed. Never force-remove, discard uncertain state or clean broad roots.

## Recovery and escalation

Git, tracker evidence and preserved worktrees are durable state; sessions are live
execution identity. Before resuming, compare tracker statuses to actual ticket and
integration commits, check ancestry and dirty work, and reconcile surviving child
sessions. A committed ticket is not necessarily integrated; an integration commit
with failed checks is not complete. Don't duplicate workers or delete uncertain work.

Kickoff covers scoped edits, checks, local branches/commits, dependency-ready
dispatch, feature merges and safe generated-worktree cleanup. Ask only for unclear
intent, scope/contract/architecture/security changes, missing credentials/provisioning,
production/deployment access, destructive work outside owned worktrees, unapproved
remote publication, exhausted repairs, unresolved verification or human QA/merge.
Worktrees do not isolate host credentials, files, processes, networks or services.
