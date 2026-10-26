# Delivery execution contract

Read the project's AGENTS.md and docs/agents/{project,issue-tracker,domain}.md when
present. For bounded tasks infer existing check commands from repository scripts;
missing profile documents alone need not trigger a setup interview. For graph
execution, establish missing checks, workspace/runtime and publication policy first.

## Host and identity

Read [CLI](CODEX-CLI.md) for standalone Codex or [T3](T3.md) inside T3 Code.
Do not apply both transports to one task. Before trusting project operations,
verify absolute workspace root, branch/detached status, expected HEAD and dirty
paths. Stop on mismatch; never reset or fall back to the user's live checkout.
Pass each child the full acceptance/spec, starting SHA, baseline, check commands,
owned scope, execution contract and commit policy. Children do not delegate.

Worktrees separate Git changes, not credentials, processes or services. Respect
actual sandbox/approval settings. Never bypass a denied operation through another
command. Read-only agent instructions do not create a read-only sandbox. Keep
secret values and raw credential-bearing configuration out of evidence.

## Commit attribution

Follow an explicit project policy first. Otherwise use `Codex Agent
<codex-agent@users.invalid>` for author and committer on agent-created commits,
with an `Agent: Codex / <actual model>` trailer. Obtain the actual model from runtime
metadata; if unavailable record `unknown`, never invent it. Set identity only for
the command, never in shared Git config. Do not use a human's signing key.

```sh
GIT_AUTHOR_NAME='Codex Agent' GIT_AUTHOR_EMAIL='codex-agent@users.invalid' \
GIT_COMMITTER_NAME='Codex Agent' GIT_COMMITTER_EMAIL='codex-agent@users.invalid' \
git -c commit.gpgsign=false commit -m 'fix(scope): describe change' -m 'Agent: Codex / <actual model>'
```

Apply the same identity/signing/trailer policy to merge commits. Fast-forwards
preserve existing attribution. Stage only owned paths and inspect the result.

## Final verification and repair

For graph execution and substantial/risky bounded changes, delegate an independent
Tester and a fresh Reviewer. Pin the feature SHA; suspend mutations while checking.
Tester covers every criterion and required command. Reviewer reads the full direct
`git diff <baseline> <final>` and spec/standards itself, not a copied diff. Provide
original check records when process evidence such as TDD chronology matters.
Missing evidence is not a pass. Keep evidence outside product history if appropriate.

Use a separate verification worktree at that exact SHA for checks that write files.
Run Tester and Reviewer concurrently only when their work and shared services cannot
interfere. Report actual permissions; use a separately launched read-only CLI session
when enforced read-only execution is required, rather than promising it for a child.

Send blockers to one focused builder based on the exact final SHA. Integrate and
rerun required final checks and fresh full-range review on the new SHA. At most two
repair passes by default, then escalate. Advisory preferences alone do not force
repair. Small direct tasks report self-checks honestly; the project can require a
stronger gate. Never silently downgrade a required independent gate.

## Handoff and recovery

Verify HEAD still equals the checked/reviewed SHA. Record baseline, final SHA,
acceptance coverage, commands/results, review kind, blockers, deviations and human
QA steps in the configured handoff record. Record whether all required gates passed.
Planning/records ignored by Git need explicit preservation before workspace removal.
Write final evidence outside the gated commit (for example an ignored local handoff
or authorized tracker). Committing a handoff after verification changes HEAD and
requires verification again; do not silently record the old SHA as the new tip.
Keep feature workspaces for QA. No deployment, protected-branch merge or remote
publication follows implicitly. After QA the owner may invoke `$ship <feature>`.

Before resuming, reconcile tracker records with commits, ancestry, dirty state and
live task state. A visible commit does not prove a worker finished. Remove only
owned, clean generated worktrees after workers finish and their commits are ancestors
of checked integration HEAD. Preserve ignored/untracked records first. Use non-force
worktree removal and `git branch -d`; preserve anything refused or uncertain.
