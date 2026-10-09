---
name: implement
description: "Deliver one clear bounded change with TDD and fresh final review, without a ceremonial spec or graph."
---

# Fast-path implementation

Read `../implement-spec/LOCAL-EXECUTION.md` for routing, gate, repair and handoff.
This is the OpenCode adaptation of the pinned upstream skill (see `../../workflow/UPSTREAM.md`).

1. Read the request and configured project profile. If a ticket is referenced,
   fetch it and state its title. Confirm concise, testable acceptance and testing
   seams **once**; an already explicit confirmation is sufficient. Work must fit
   one fresh implementation context with no unapproved contract/architecture/security
   change or meaningful dependency graph. Otherwise return to planning, not silent
   scope expansion. Do not manufacture a spec or tickets for a bounded change.
2. The clear request plus acceptance confirmation authorizes delivery. Pin the
   baseline and verify setup/checks. Preserve the normal checkout and `main`;
   create a uniquely named generated feature branch/worktree for this change.
   Move the Coordinator's Location and confirm identity there.
3. Dispatch one `builder` directly in that worktree using the child routing
   protocol. Supply the request/acceptance, project profile, exact identity and
   relevant checks. It loads `tdd`, reviews its diff and creates focused commits.
4. Validate exact final SHA and required checks. Run independent final Tester and
   fresh Reviewer against the request/acceptance as the spec source, following
   LOCAL-EXECUTION.md. Apply its bounded repair rules; no routine intermediate gate.
5. Hand back the verified branch/commit, results and QA instructions. Publish only
   when configured. The user owns QA and merge into `main`.
