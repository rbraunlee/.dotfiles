# Issue tracker: Local Markdown

Default tracker. One feature per `.scratch/<feature-slug>/` directory:

- Spec: `spec.md`; approval records the exact agreed revision/reference.
- Tickets: `issues/<NN>-<slug>.md`, stable IDs from `01`, one file per ticket.
- Every ticket references its spec/acceptance IDs, blockers, relevant checks,
  high-risk review requirement (if any), and a **Status:** line.
- Read/fetch: read the named file and appended comments.
- Publish: create/update only the named planning files, preserving user content.
- Claim: set `in-progress` before launching one Implementer; record its branch,
  worktree, dispatch SHA and session ID in an appended execution comment.
- Blocked: set `blocked` with evidence; keep the worktree/session references.
- Complete: set `integrated` only after the exact ticket SHA is integrated and
  integration checks pass. Append ticket/integration SHAs and check outcomes.
- `ready-for-agent` means planned and available, not kickoff or completed work.

Blocking edges reference stable ticket IDs. The frontier contains incomplete,
unclaimed tickets for which every blocker is integrated and checked. A ticket
commit alone never unblocks dependants. On resume reconcile recorded status with
Git/worktree/session evidence before dispatch. Append comments under `## Comments`;
do not replace history or delete specs/tickets after approval or handoff.

The Coordinator updates one canonical tracker in the feature worktree. Copies in
ticket worktrees are read-only context snapshots, not competing status writers.
Persist local tracker changes with focused commits on the feature branch; keep
them available for recovery and human QA. If `.scratch/` is ignored by project
policy, keep the authoritative files in the preserved feature worktree and report
that path; do not silently force-add files or rely on ticket copies for recovery.
