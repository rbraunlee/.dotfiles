# Alignment — feature delivery workflow

**Status:** approved direction, 2026-10-06. The executable adoption sequence is in
[workflow-plan.md](workflow-plan.md); terminology is in [CONTEXT.md](CONTEXT.md).
The previous S0 and custom-launcher design is superseded; historical revisions
remain available in Git.

## Intended outcome

The user acts primarily as product owner and QA: discuss intent, approve the
destination and execution graph, issue one kickoff, then inspect the completed
feature. Routine implementation decisions, ticket dispatch and newly unblocked
work do not require repeated approval.

## Decisions

1. **Feature-level authorization.** Approval of the spec and ticket graph plus one
   explicit `implement-spec` instruction authorizes the complete graph. The user
   does not approve tickets individually.
2. **Two paths.** Clearly bounded one-context work uses a fast implementation path.
   Larger or ambiguous work uses a feature spec and dependency-aware ticket graph.
3. **One planning context.** Brainstorming is optional; grilling, spec synthesis and
   ticketing compose in one session instead of mandatory phase-agent handoffs.
4. **Skills own method.** Vendor a reviewed upstream skill snapshot, adapt it
   minimally for OpenCode and keep agent prompts as thin authority contracts.
5. **Flat execution roles.** One feature Coordinator directly launches ticket
   Implementers and Merger/final-verification agents. There is no nested Slice
   Orchestrator layer.
6. **Worktrees.** Use a feature integration worktree and one worktree per active
   ticket. OpenCode child sessions move their Location to the assigned worktree and
   verify it before acting. Multiple features may run concurrently.
7. **Feature-level assurance.** Implementers use TDD and the Merger checks each
   integration. Independent Tester and Reviewer gate the completed feature. Add
   ticket-level independent review only for explicitly high-risk work.
8. **One feature PR.** Do not create slice PRs by default. Create one feature PR
   when the configured project workflow uses hosted review.
9. **No launcher initially.** Git, tracker records, worktrees and OpenCode sessions
   provide initial execution and recovery state. Add deterministic machinery only
   for demonstrated recurring failures.
10. **Routine work is pre-authorized.** The kickoff covers normal local edits,
    checks, branches, commits, feature integration and safe generated-worktree
    cleanup. Escalate contract/scope/security changes and dangerous or human-only
    actions, not routine shell commands.
11. **Per-project tracker setup.** Configure the tracker once per repository, with
    local Markdown as the default and GitHub or another tracker available.
12. **Human final control.** The user performs final QA and the merge into `main`.
    No production access or deployment is authorized.

## Safety boundary

Initial execution is trusted local development. Worktrees, branches and role
permissions organize work but do not isolate host files, credentials, processes,
networks or shared services. Sandboxing remains a separate future project and is
neither claimed nor required by this workflow.

## Escalation boundary

Agents may revise implementation details while preserving approved behavior,
scope and constraints. They pause for ambiguous or conflicting product intent,
changes to shared contracts/architecture/security, missing human-only access,
unapproved publication or production actions, persistent failed verification and
the final QA/merge decision.

## Current implementation status

The installed agents and reviewed skills now implement this direction. Trusted-local
routing, fast-path delivery and dependency-graph delivery have been verified;
evidence and observed limitations are in [workflow-adoption.md](workflow-adoption.md).
Implementation files remain uncommitted pending human review. This is not a claim
of security isolation, hosted-publication validation or automatic merge into `main`.
