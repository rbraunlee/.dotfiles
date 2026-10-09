# Glossary — agent-assisted feature delivery

These terms belong to the active [workflow plan](workflow-plan.md) and
[alignment](alignment.md). Superseded S0 and launcher terminology is not part of
the active workflow; historical revisions remain available in Git.

## Planning

- **Feature**: A coherent product outcome reviewed and accepted as a whole.
- **Feature spec**: The authoritative description of a feature's intended behavior,
  acceptance criteria, constraints, testing expectations and exclusions.
- **Ticket**: A bounded, independently implementable contribution to a feature,
  normally expressing a thin end-to-end behavior.
- **Ticket graph**: A feature's tickets and their blocking relationships.
- **Frontier**: The incomplete tickets whose blockers are all complete and which
  are therefore available for implementation.
- **Approved planning package**: The feature spec and ticket graph accepted by the
  user as the basis for execution.
- **Feature kickoff**: The explicit instruction authorizing execution of an entire
  approved planning package.
- **Fast path**: Direct delivery of one clear, bounded change without manufacturing
  a feature spec or ticket graph.
- **Shared contract**: An agreed interface or behavior relied on by more than one
  ticket, component or feature.
- **High-risk ticket**: A ticket whose concrete correctness, security or integration
  risk warrants independent review before feature completion.

## Execution

- **Trusted local execution**: Approved development work running on the host without
  security containment of files, credentials, networks, processes or resources.
- **Coordinator**: The role owning one approved feature's scheduling, integration,
  final verification and handoff.
- **Implementer**: The role owning one ticket or fast-path change, including tests,
  implementation, scoped refactoring and focused commits.
- **Merger**: The role integrating completed ticket work and verifying the combined
  feature state.
- **Tester**: The independent role executing checks and assessing acceptance
  coverage without changing product code or committed tests.
- **Reviewer**: A fresh read-only role assessing the completed change against its
  approved requirements and applicable standards.
- **Feature integration branch**: The branch assembling a feature's ticket
  contributions before human acceptance.
- **Feature worktree**: The checkout of the feature integration branch used to
  assemble and verify the feature.
- **Ticket worktree**: A separate checkout and branch assigned to one ticket's
  Implementer.
- **Repair pass**: Focused corrective implementation addressing blocking final
  verification findings without changing the approved contract.
- **Blocking finding**: An unmet requirement or concrete defect or risk that
  prevents completion.
- **Advisory finding**: A non-required improvement or preference that does not
  prevent completion.

## Acceptance

- **Feature gate**: Independent testing and review of the completed integration
  branch against the full feature spec.
- **Feature PR**: The hosted review and acceptance record for the integrated feature
  proposed for `main`.
- **QA-ready**: A feature that has passed its feature gate and is presented for
  human inspection with exact references and a QA checklist.
- **Human QA**: The user's assessment of intent, usability and the finished outcome,
  distinct from automated checks and independent code review.
