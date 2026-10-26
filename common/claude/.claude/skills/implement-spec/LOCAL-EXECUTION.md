# Claude Code local execution contract

Shared by `implement-spec` and `implement`. This is a prompt-driven workflow, not
a launcher, scheduler, ledger or sandbox. Roles read project configuration from
`docs/agents/{project,issue-tracker,domain}.md` (or explicit project instructions).
Missing setup/checks become setup work; never silently waive them.

## Agent-created commits

For every commit a Claude Code delivery agent creates (Coordinator tracker/recovery
commits, Implementer tickets and repairs, Merger integration/conflict commits, and
optional assigned refactoring), use `Claude Agent <claude-agent@users.invalid>`
for **both author and committer**. Set all four identity variables per command,
not with `export`, `git config`, or a persistent shell/session setting. Use the
creating agent's **actual model ID** (from your environment, e.g. `claude-sonnet-5-5`),
not a role default or another agent's model, in the final
`Agent: Claude Code / <actual model ID>` trailer. Claude Code may also add its own
`Co-Authored-By` trailer; keep it, but the `Agent:` trailer must be present.
Replace the angle-bracketed placeholders:

```sh
cd '<assigned-worktree>' && GIT_AUTHOR_NAME='Claude Agent' GIT_AUTHOR_EMAIL='claude-agent@users.invalid' \
GIT_COMMITTER_NAME='Claude Agent' GIT_COMMITTER_EMAIL='claude-agent@users.invalid' \
git -c commit.gpgsign=false commit -m 'fix(scope): describe change' -m 'Agent: Claude Code / <actual model ID>'
```

The same per-command identity, `-c commit.gpgsign=false`, and own-model trailer
apply to any Git operation that **creates** a commit, including non-fast-forward
merges: supply the trailer in the merge message when a merge commit is needed.

```sh
cd '<feature-worktree>' && GIT_AUTHOR_NAME='Claude Agent' GIT_AUTHOR_EMAIL='claude-agent@users.invalid' \
GIT_COMMITTER_NAME='Claude Agent' GIT_COMMITTER_EMAIL='claude-agent@users.invalid' \
git -c commit.gpgsign=false merge --no-ff --no-gpg-sign '<ticket-branch>' -m $'Merge ticket branch\n\nAgent: Claude Code / <actual model ID>'
```

Fast-forward integration creates no new commit: preserve the ticket commit's
existing attribution. Do not use an automatic commit-producing cherry-pick or
revert that omits the required trailer; use a no-commit form followed by an
attributed commit if the operation is authorized. Inspect the resulting commit.
Never use the human's personal signing key, change global or shared repository
identity settings, guess or overwrite existing attribution, or rewrite history.
This is identification, not a cryptographic signature; follow the project's
scope and protected-branch rules independently.

Read required supporting files with the Read tool. If a read, hook or permission
check denies an operation, stop and report it; do not retry via another command,
tool, path or copied contents to bypass the denial. The user may authorize a
narrow policy correction.

## Worktrees

Default worktree root: `~/.local/share/claude-worktrees/<project>/` (the user
settings grant it as an additional working directory). Name the feature worktree
`<feature>` and ticket/repair/verification worktrees `<feature>--<ticket-or-purpose>`.
Create them with `git worktree add -b <branch> <absolute-path> <exact-sha>` from
the primary checkout. Do **not** use the Agent tool's `isolation: "worktree"` or
`EnterWorktree` to create delivery worktrees: they branch from the default branch
or parent HEAD, not from the exact assigned SHA, and Claude Code may sweep them.

## Routing every child

Subagents start in the parent's primary working directory and **never keep a
`cd` between Bash calls**. Supply the exact absolute assigned worktree path,
branch or detached-HEAD status, expected start SHA, baseline, requirements, check
commands and scoped authority. The child must:

1. Start **every** Bash call with `cd '<assigned-worktree>' && `.
2. Use only absolute paths inside the assigned worktree for Read/Edit/Write/Glob/Grep.
3. As its first call, run and report from that worktree:

   ```sh
   cd '<assigned-worktree>' && pwd && git rev-parse --show-toplevel && git branch --show-current && git rev-parse HEAD && git status --short
   ```

   and compare every value with the assignment before reading or editing project
   files. Stop on any mismatch; no reset, original-checkout fallback or broad
   permissions.

The policy hook (`~/.claude/hooks/policy.py`) refuses delivery-role commands and
edits whose effective directory is a primary checkout, so a missing `cd` fails
loudly instead of touching the user's checkout. `git -C` and a prompt path are
not routing evidence. The Coordinator verifies the child's reported identity
independently before trusting its work.

The Coordinator may continue an existing **idle** child with `SendMessage` (by its
agent ID) instead of starting a duplicate, but must still obtain the child's own
identity confirmation. Children receive their own tools and the hook's per-role
limits, not the parent's. Delivery children do not launch further agents.

Background dispatch is preferred in an interactive session: the Agent tool notifies
the Coordinator when a child finishes. In a non-interactive `claude -p` run, use
foreground children unless durable continuation has been demonstrated; returning
a waiting summary ends that invocation and is not a QA-ready handoff. Do not start
a duplicate worker merely because the original invocation disconnected.

## Final verification

1. Pin the completed integration SHA. No implementation or integration may mutate
   it while the gate is running. Give `tester` the full spec/acceptance and all
   agreed commands; give a fresh `reviewer` the full spec, standards, exact baseline
   and final SHA. Both confirm their routing and Git identity first.
2. Tester accounts for every criterion and runs agreed checks. Reviewer loads
   `spec-review` and inspects the complete two-dot `git diff <baseline> <final>`
   directly using read-only Git, reporting spec and standards axes independently.
   No copied/truncated diff is a substitute. A missing check, review, criterion or
   unresolved blocker is not a pass; advisory preferences do not force repair.
   For process findings such as TDD chronology, give the Reviewer the Implementer's
   original check results and agent ID. If a report omits evidence, ask the same
   child via `SendMessage`, or read its transcript (`subagents/agent-<id>.jsonl`
   under the session's directory in `~/.claude/projects/`) read-only, before
   dispatching repair or asking for a waiver. Preserve original commands, outputs
   and ordering; don't fabricate history or confuse a post-hoc reconstruction with
   a contemporaneous run. Transcripts need not be committed to product history.
   A missing pointer is not proof that no record exists.
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

- On pass, verify integration HEAD still equals the tested/reviewed SHA and report
  the local feature branch and SHA. The Coordinator opens no PR: in `Ship mode: pr`,
  `/ship` creates the one feature PR after human QA (with spec/ticket references).
  If hosted publication is explicitly enabled by setup, the Coordinator may push
  only the feature branch. Permission prompts still apply: denied publication is
  a reported blocker, not permission to broaden rules. No automatic `main` merge.
- Report baseline, final SHA, acceptance coverage, commands/outcomes, independent
  review, deviations, risks and a short project-appropriate QA checklist. Provide
  inspect/run instructions; do not leave a persistent preview running unless
  requested or pre-authorized. Record the tested/reviewed SHA and QA checklist in
  the feature's handoff/approval record; `/ship` pre-flight compares that SHA.
  The user performs QA. End the handoff with: after human QA, run `/ship <feature>`
  (owner-invoked; the only agent path to `main`).
- Keep the feature worktree for QA. Only clean, owned, successfully verified
  generated ticket/repair/verification worktrees with finished children may be
  safely removed. Never force-remove, discard uncertain state or clean broad roots.

## Recovery and escalation

Git, tracker evidence and preserved worktrees are durable state; agents are live
execution identity. Before resuming, compare tracker statuses to actual ticket and
integration commits, check ancestry and dirty work, and reconcile surviving
children (`ListAgents` where available). A committed ticket is not necessarily
integrated; an integration commit with failed checks is not complete. Don't
duplicate workers or delete uncertain work.

Kickoff covers scoped edits, checks, local branches/commits, dependency-ready
dispatch, feature merges and safe generated-worktree cleanup. Ask only for unclear
intent, scope/contract/architecture/security changes, missing credentials/provisioning,
production/deployment access, destructive work outside owned worktrees, unapproved
remote publication, exhausted repairs, unresolved verification or human QA/merge.
Worktrees do not isolate host credentials, files, processes, networks or services.
