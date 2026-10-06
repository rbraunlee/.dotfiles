> **Historical copy (2026-10-06)** of root `docs/plan-change-proposal.md`. Proposal at drafting time; its direction was later approved separately, but its cleanup advice and older snapshot are historical.
> Original root note remains ignored and untouched. Paths written as `docs/...` below refer to original drafting locations; use [the package history index](../README.md) for relocated files.

# Plan-change proposal: prove the workflow before building the platform

**Status:** Proposal only; not yet approved or implemented  
**Date:** 2026-10-06  
**Purpose:** Replace the current W1–W9 implementation-first trajectory with a
small end-to-end proof, then add automation only in response to observed failures.

## Why change the plan

The product value is the delivery workflow:

> feature intent → slices → one-slice Orchestrator (Builder, Tester, Reviewer) in
> its own clone → verified integration → human merge

The roles, prompts and skills are the primary workflow experience. The launcher is
intended to be narrow and deterministic, not a general orchestration platform.

The current plan specifies substantial infrastructure before proving that one real
slice through the workflow is useful: immutable bundle snapshots, session and command
tracking, durable lifecycle state, recovery, GitHub operations, concurrency, and
multiple identity-bound evidence records. Some may prove necessary, but they should
not all be prerequisites for the first proof.

This proposal does not reject the longer-term workflow or discard W1/W2 work. It
changes the order of investment: first demonstrate the value manually, then let
observed friction justify each additional mechanism.

## Proposed implementation sequence

### S0 — One end-to-end slice, mostly by hand

Use one approved feature with one bounded slice in a trusted, disposable project.
Use the current roles/prompts/skills and one independent clone for the slice.
Manually coordinate the Orchestrator, Builder, Tester and Reviewer; run the relevant
checks; inspect the result; verify the integrated candidate; and leave the final merge
to the user.

Keep the process intentionally simple:

- No automatic multi-slice scheduling or parallel workers.
- No general launcher abstraction, durable ledger, bundle identity, or OpenCode HTTP
  session/command tracker.
- No credential broker, network policy, retention system, or security-isolation
  claims.
- Manual steps or a small task-specific script are acceptable. Do not target a line
  count; automate only a step whose repetition or failure justifies it.
- Keep production credentials/data, deployment and autonomous main-branch merges
  out of scope. A clone and role prompt are workflow aids, not a security boundary.

**S0 proves:** the roles can complete a real slice; the clone/session arrangement is
usable; checks and independent review provide useful feedback; and the integrated
result can be verified and handed to the user for acceptance. Record friction,
failures and manual workarounds, but do not build infrastructure merely to produce
formal evidence of the experiment.

### S1 — Address only failures observed in S0

Review the S0 notes and add the smallest correction for a demonstrated failure.
Possible candidates include duplicate claims or work exceeding a useful time limit,
but neither is presumed necessary until the trial shows it. Keep each change narrow
and test the specific failure it addresses.

### S2 — Automate integration protection if warranted

If manual candidate verification is error-prone or repeatedly costly, automate the
narrow verify-before-publish step: verify a disposable candidate, then advance the
feature branch only if the expected head is unchanged. Until then, perform the check
manually and keep the final merge human-controlled.

### S3+ — One observed failure at a time

Every later feature must cite the concrete S0/S1/S2 failure or repeated friction it
addresses, explain why a smaller remedy is insufficient, and include a way to verify
the remedy. Do not add an abstraction or platform capability solely for hypothetical
future scale.

## Change discipline

1. Run S0 before expanding the launcher or implementing the remaining W milestones.
2. Preserve current W1/W2 source, tests and evidence as experimental work; do not
   delete it or assume it is the foundation of the revised workflow.
3. After S0, compare each existing component with an observed need. Reuse, simplify,
   defer or retire it deliberately; do not port the whole package by default.
4. Keep workflow policy tool-independent where practical. Treat OpenCode-specific
   commands, skills, agents or plugins as adapters, and add them only when the
   platform feature solves a demonstrated problem.
5. Keep the proposal and resulting plan explicit about what is manual, automated,
   verified, deferred and not a security guarantee.

## Proposed repository and commit cleanup

Current working-tree snapshot when this proposal was drafted:

- `main` is at `594baa7`, matching `origin/main`.
- Ten agent configuration files are modified.
- `linux/opencode-routine/` is untracked (the earlier analysis counted 71 files).
- `docs/` is ignored/untracked, so this proposal will not travel with Git unless
  documentation tracking is addressed.

Recommended cleanup sequence:

1. **Close the permission regression separately.** The current edits still leave
   `planner.md` and `tutor.md` using the unsupported agent-frontmatter key
   `permissions:`. Correct their intended restrictions using the supported
   `permission:` form, then verify the resolved rules with `opencode debug agents`.
   Commit this narrow safety fix independently of the workflow reset.
2. **Separate unrelated agent edits.** Review and commit permission-format changes,
   Draw.io instruction changes, and model changes separately. Hold further model
   changes until their recurring cost/quality tradeoff is decided. Do not amend or
   rewrite existing commits as part of this cleanup.
3. **Preserve the launcher experiment.** Keep W1/W2 source and tests recoverable on a
   clearly named local experiment/checkpoint branch. Do not merge it into the new
   S0 path wholesale. Do not delete, reset or discard the untracked package.
4. **Replace the active plan without erasing history.** Make this proposal the basis
   for a concise active S0–S3 plan if accepted. Retain the W1–W9 plan and its evidence
   as historical material, clearly labeled as superseded for the active direction.
5. **Resolve documentation tracking intentionally.** Decide which decision and plan
   documents should be versioned, then adjust ignore rules or stage only those
   selected files. Do not blindly add the entire `docs/` tree.
6. **Keep commits reviewable.** Use focused commits for the safety fix, any accepted
   agent-config changes, the plan reset, and later S0 implementation. Avoid combining
   the launcher experiment, unrelated agent edits and the new plan into one commit.

## Approval boundary

This document is a proposal. It does not itself authorize changing agent
configuration, moving branches, staging or committing files, deleting W1/W2 work,
running a workflow trial, or implementing S0. Those actions require the user's
separate direction.
