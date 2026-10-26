---
name: ship
description: Ship one verified feature after explicit human QA approval, using the project's local merge or PR policy.
---

Read the project profile and [execution contract](../implement-spec/LOCAL-EXECUTION.md).
Invocation is not QA approval, but an explicit QA approval already supplied for the
same feature and SHA is sufficient. Do all read-only preflight work before requesting
any missing approval. Do not ask again for authorization already recorded.

1. Resolve one feature branch, baseline, final SHA, workspace and handoff record.
   Read the configured protected branch and `Ship mode: local-merge | pr`; ask if
   missing. Work from the primary checkout, outside any workspace to be retired.
   Require clean primary and feature workspaces, feature tip equal to recorded
   checked/reviewed SHA, all project-required gates passed, and no unresolved blockers.
   Confirm the protected branch is checked out in the primary workspace. In PR
   mode inspect existing PR state before applying ancestry checks: for an already
   merged PR use step 4's merged-PR checks; otherwise require the protected branch
   to be an ancestor of the feature tip. On mismatch stop; do not reset, switch branches,
   repair, rebase or silently reuse stale evidence.
2. Present the QA checklist, exact proposed merge/publication and retirement paths.
   For GNU Stow projects explain which live packages change immediately and which
   added files require re-stowing. Obtain only missing explicit QA/shipping approval.
3. In local-merge mode, merge the exact verified SHA with `--no-ff`, an appropriate
   Conventional Commit message and project attribution. On conflict abort the merge
   and verify the original primary HEAD/clean state; report failure, never resolve
   conflicts on the protected branch. Never push the protected branch.
4. In PR mode, first inspect the exact feature's existing PR and remote head. An open
   PR is reported, not duplicated. A closed-unmerged PR blocks automatic publication.
   With no PR and authorized publication, push only the feature branch and create
   one PR against the configured base. Register it with the host when supported.
   Report its URL and retain workspaces while open; do not merge it. For an already
   merged PR, confirm its reviewed head equals the recorded final SHA and its merge
   is present in the local protected branch before retiring. Fetch/update requires
   applicable authorization; uncertain squash/rebase ancestry means preserve work.
5. Before retirement, reconcile live task/process state using the applicable host
   reference. Preserve all named ignored/untracked planning and QA records in the
   configured durable location. Never overwrite differing records: compare copies
   by checksum and stop retirement on mismatch. Keep dirty/in-use/uncertain workspaces.
   Remove only owned clean worktrees non-forcibly and branches with `git branch -d`.
   A deletion refusal is a preserved artifact, not permission to force removal.
6. Report merge SHA or PR URL, checks and QA evidence, retained artifacts, and any
   reload/re-stow steps. For local merge, report ahead/behind state when an upstream
   exists; do not assume origin/main. Do not delete historical decisions or evidence.
