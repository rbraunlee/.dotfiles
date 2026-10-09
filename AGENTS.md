# Agent skills

Read the project profile before planning or delivery:

- [Project checks, scope and runtime policy](docs/agents/project.md)
- [Local tracker and completion semantics](docs/agents/issue-tracker.md)
- [Domain vocabulary and decision records](docs/agents/domain.md)

Planning approval is not execution kickoff. Implementation requires a separate
explicit instruction naming the approved spec. Keep cleanup features separate by
environment group and Stow package; preserve unrelated configuration and history.

Root documentation under `docs/` is local-only under the existing ignore policy.
Ignored or uncommitted planning inputs must be supplied explicitly to generated
worktrees; do not assume they are present in a checkout of the baseline commit.
