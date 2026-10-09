---
name: implement-spec
description: "Deliver an explicitly approved feature spec and ticket graph with worktree-routed Implementers, serialized integration and independent final verification."
---

# Implement a feature

OpenCode adaptation of the pinned Matt Pocock skill; provenance and changes are in
`../../workflow/UPSTREAM.md`. Read [local execution](LOCAL-EXECUTION.md) before acting.

## Kickoff and prepare

1. Read the full spec, all tickets/blocking edges and `docs/agents/` profile. Confirm
   the user approved the planning package and explicitly kicked off this feature.
   Planning approval alone does not authorize implementation. Reject unknown
   blockers, cycles, duplicate IDs or ambiguous acceptance before dispatch.
2. Reconcile existing tracker, branches, worktrees and sessions first on a resume.
   Do not duplicate an active/uncertain Implementer. Completion means successfully
   integrated and checked work, not just a ticket commit or a claimed status.
3. Pin the baseline SHA and record the normal checkout's branch/HEAD/dirty paths.
   Validate setup and baseline checks. Create a uniquely named feature integration
   branch and worktree from that SHA, leaving the normal checkout untouched. Use
   the project's branch/root policy (default root `/tmp/opencode/<project>/<feature>`).
   Move the Coordinator's Location there and verify identity. Never reset a mismatch.
4. Ensure the spec, tickets and profile are readable in each worktree. Local ignored
   or uncommitted planning files do not appear automatically: copy only the named
   planning inputs into generated worktrees or supply their full contents. Record
   source/revision; do not copy unrelated changes or rely on inaccessible pointers.

## Work the graph

1. Compute the frontier: incomplete, unclaimed tickets whose blockers are all
   integrated and checked. Dispatch up to the configured concurrency (default two).
   Respect shared-service/port/database limits; serialize when no safe policy exists.
2. Mark the ticket in-progress in the configured tracker before dispatch. Create a
   unique ticket branch/worktree at the exact current integration SHA. Directly
   launch `builder` children, preferably in background, using the routing protocol
   in LOCAL-EXECUTION.md. Supply pointers/full inputs, expected Git identity,
   applicable acceptance and checks. The child loads `tdd` and commits only its work.
3. Validate each returned final SHA, branch ancestry, actual worktree state and
   required checks only after the assigned child has finished and reported its
   result. A clean worktree or visible commit is not evidence that a worker has
   stopped; never integrate, dispatch a duplicate, or remove its worktree while it
   may still be writing. Failed/missing evidence blocks integration; preserve work.
   Add independent ticket review only for an explicitly high-risk ticket. Escalate
   newly discovered product/security risk rather than changing requirements.
4. Directly launch one `merger` in the feature worktree with its expected current
   HEAD and the completed exact ticket SHA. Never run two Merger mutations together.
   Other tickets may continue against their dispatch baseline; the Merger handles
   implementation-only conflicts against the current tip. Product/contract conflicts
   block. Run configured integration checks before marking a ticket complete.
5. On successful integration, record the ticket and integration SHAs/check results
   in the tracker, mark integrated (or equivalent hosted state), recompute the
   frontier and dispatch newly ready work without another human prompt. A hosted
   tracker that closes on PR merge remains open with integration evidence until
   human merge; do not call it closed prematurely.
6. Remove only clean, owned generated ticket worktrees whose exact commits are
   ancestors of the checked integration HEAD and whose sessions have finished.
   Use non-force `git worktree remove <exact-path>`; retain the branch/traceability.
   Preserve failed, interrupted, dirty or ambiguous worktrees. Reconcile tracker
   evidence before retrying if a tracker write fails after successful integration.
7. Repeat until every ticket is integrated or no safe progress is possible. An
   empty frontier with incomplete work is blocked, not completion.

## Final gate and handoff

Use the final verification, repair and publication procedure in LOCAL-EXECUTION.md
against the full spec and exact integration commit. One feature-level gate and,
when authorized, one feature PR; never routine per-ticket PRs or human approvals.
