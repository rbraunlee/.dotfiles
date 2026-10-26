---
name: implement
description: Deliver a bounded code or configuration change with proportionate checks and an exact-commit handoff.
---

Read [execution contract](../implement-spec/LOCAL-EXECUTION.md). Reuse acceptance
already explicit in the request; ask only about consequential ambiguity. A clear
implementation request authorizes scoped edits and required checks. Do not invent
a spec, ticket graph or repeated approval gate.

For a small reversible change, work directly on the user's requested feature
branch/workspace and run relevant checks. Do not spawn agents or manufacture tests
for wording-only changes. Use TDD when requested or agreed, not for every edit.
For substantial or risky changes, use an isolated feature workspace and delegate
independent Tester and fresh Reviewer checks as described in the contract. Explicit
project requirements for independent verification still apply to small changes.

Preserve unrelated work. Commit scoped changes when authorized by the delivery
request/project conventions; otherwise report the diff and that no immutable
commit was verified. Hand off acceptance coverage, checks and limitations. Never
label self-review as independent review. Shipping requires a committed final SHA;
a required independent gate cannot be silently waived. Use implement-spec when
real dependencies require multiple implementation contexts.
