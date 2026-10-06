# Workflow-first plan — prove one slice

**Direction approved 2026-10-06; S0 calculator trial ran and was locally accepted.**
See the [dated S0 record](archive/calculator-s0-2026-10-06.md) for outcomes and
limits. This is the active implementation order, not a claim that later workflow
automation or sandbox gates have passed. The longer-term
product contract remains in [alignment.md](alignment.md); terms are in
[CONTEXT.md](CONTEXT.md). The W1–W9 launcher sequence, W1 acceptance, assembled but
not real-qualified W2 source/tests and earlier M1/M2 sandbox evidence are dated
history on `experiment/opencode-routine-w1-w2-checkpoint` under
`linux/opencode-routine/docs/`. Do not merge that branch wholesale or treat its
tests as S0 or real W2 qualification.

## Preparation for the first trial (completed)

1. Obtain separate approval for one feature and a bounded, dependency-ready slice
   in a trusted, disposable project. Record the exact feature baseline commit/ref,
   the spec, slice ticket, applicable acceptance criteria, approved development
   inputs, required slice **and combined-candidate** checks and acceptance handoff.
   Resolve missing checks before starting; never revise requirements just to pass.
2. In separately authorized work, the active Orchestrator, Builder and Tester
   legacy-loop instructions were replaced and a fresh read-only Reviewer added
   before the first trial. The preparation plan itself did not rewrite prompts or
   authorize a trial. The later permissions/routing/diff correction was verified
   offline, not real-qualified; verify effective permissions and actual clone/tool
   routing on future runs.

## S0 — one real slice, mostly manual

1. **Prepare:** The one-slice Orchestrator creates an independent clone with its
   own `.git` metadata and a slice branch at the recorded baseline. Ensure Builder,
   Tester and Reviewer actually operate in that clone; a path in a prompt is not
   proof. Give them the approved spec, ticket, criteria and checks.
2. **Build:** Builder implements the slice and tests, performs scoped refactoring
   and makes clean commits. No separate mandatory Refactorer/Cleaner phases.
3. **Verify:** Tester independently runs agreed relevant tests, lint/type checks
   and build where applicable and accounts for acceptance criteria without editing
   product code or committed tests. A **fresh**, read-only Reviewer independently
   examines the final change against the requirements and applicable standards.
   Missing checks/review and unresolved blockers do not count as passes.
4. **Repair or escalate:** Orchestrator may give concrete findings to Builder for
   **at most two** repair attempts after the initial implementation. After each
   repair, rerun affected checks and review the resulting final commit. Escalate
   persistent blockers and any proposed change to approved scope, requirements or
   shared contracts. Retain failed/interrupted work and report uncertainty.
5. **Verify integration:** Orchestrator prepares a disposable combined candidate
   from the final slice and recorded feature state, records its exact commit and
   runs the pre-agreed integration checks on that commit. Check that the expected
   feature head has not moved; a changed head, failed check or missing review stops
   publication. Slice-only success does not prove the combination succeeds.
6. **Hand off:** Report baseline, final slice range/commit, candidate commit,
   acceptance coverage, checks, independent review, deviations and risks. The user
   controls feature-head publication and the final merge into `main`. Do not
   automatically publish a feature branch, merge, deploy or start QA.

S0 succeeds only if the slice and the exact combined candidate pass their agreed
checks, applicable criteria are covered, and independent testing/fresh review have
no unresolved blockers at the final commit. A blocked or incomplete trial is useful
learning, **not** a pass; record friction and manual workarounds honestly.

**Safety:** Trusted local execution only. A clone and role permissions are workflow
aids, not isolation of files, credentials, networks or processes. No production
data/access, deployment, sandbox fallback or host-security claim is authorized.
Agree on appropriate development access and commands before running anything.

## After observing S0

The [2026-10-06 power-shortcut follow-up trial](archive/calculator-power-2026-10-06.md)
passed its reported slice and candidate checks and was locally merged by the user.
It also exposed persistent permission prompts. Human-approved guarded local fetch
and optional, separately approved cleanup are proposed/in progress as follow-up,
**not proved or completed by that trial**.

Address a concrete failure or recurring friction with the smallest verified fix;
prefer a manual remedy unless automation is justified. If candidate verification
or guarded feature-head publication proves error-prone, consider automating only
disposable-candidate checks and an expected-head-checked advance. Keep the final
merge human-controlled. Reuse, simplify, defer or retire W1/W2 components one
observed need at a time; scheduling, durable ledgers, immutable bundle systems,
HTTP session trackers and general launcher abstractions are not S0 prerequisites.
Sandbox/runtime gates in the historical design are **deferred for S0**, not passed,
waived for a later sandbox project, or grounds to run sandbox requests locally.
