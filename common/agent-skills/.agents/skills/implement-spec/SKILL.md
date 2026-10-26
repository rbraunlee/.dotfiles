---
name: implement-spec
description: Deliver an approved feature graph with isolated workers, serialized integration and independent final verification.
---

Read [execution contract](LOCAL-EXECUTION.md) and the applicable host reference.
Spec/graph approval alone does not start implementation; an explicit delivery
request does. One kickoff covers routine local work within that scope.

1. Read the full spec, graph and project profile. Reject unknown blockers, cycles,
   duplicate IDs or uncovered acceptance. Reconcile existing work and task state
   before dispatch; do not duplicate active or uncertain workers.
2. Pin the baseline and check the project baseline. Use an isolated feature branch
   and workspace. Follow the host's binding procedure; verify root, branch and SHA.
   Supply committed planning inputs or copy only named ignored/uncommitted inputs
   with their source/revision. Never assume they appear in a new worktree.
3. Dispatch builder children for dependency-ready tickets, at most the configured
   concurrency (default two). Each starts from the exact current integration SHA,
   receives the full spec and assigned acceptance, and owns a separate workspace.
   Serialize if shared services or workspace routing cannot support concurrency.
4. After a worker finishes, verify its exact final SHA, ancestry, workspace state
   and required checks. Integrate that SHA into the feature branch yourself, one
   integration at a time. Resolve implementation-only conflicts; escalate product
   or contract disagreements. Apply commit attribution to any merge commit.
5. Run integration checks before marking a ticket integrated. Record ticket and
   integration SHAs and outcomes in the tracker. A commit or failed merge/check is
   not completion. Recompute the frontier; an empty frontier with pending tickets
   is blocked. Preserve interrupted/dirty work.
6. When all tickets are integrated, run independent Tester and fresh Reviewer
   against the full feature at the same immutable final SHA. Follow the contract's
   repair, handoff and cleanup rules. Keep the feature workspace for human QA.

No routine ticket PRs, nested coordinators or per-ticket human approval cycle.
