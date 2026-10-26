# Standalone Codex execution

Start the coordinator in the intended feature workspace. The installed CLI supports
`codex --worktree` for a managed worktree and `codex --cd /absolute/worktree` for an
existing checkout. Confirm the actual resulting root/branch/HEAD; do not assume a
managed branch name. Respect a feature branch explicitly requested by the user.

Native children share the parent's permissions. Do not assume spawning creates an
isolated checkout. For independent writing contexts, use a host-supported workspace
binding or separately launch Codex with `--cd` into an explicitly created ticket
worktree. If no reliable child binding exists, serialize work in the verified feature
workspace; do not run parallel writers merely with different prompt paths.

For a separately launched worker, supply a complete assignment and the appropriate
installed role instructions explicitly. `codex exec --cd <worktree> --json` can
provide original tool records; retain its process/session ID, exit status and output.
An idle/disconnected parent is not evidence that the process finished. Bound waits,
inspect completion and preserve uncertain state instead of launching a duplicate.

For an enforced read-only review, launch a separate session with `--sandbox read-only`
and the full review assignment. A tester may need workspace-write for generated
artifacts. Failures needing unavailable approval are blockers, not permission to
relaunch unrestricted. Do not change the parent's security settings silently.

Before removing a workspace, reconcile workers you launched with available session
and process state. Persisted history alone is not a live worker. If ownership or
liveness cannot be established, keep the workspace and report the uncertainty.
