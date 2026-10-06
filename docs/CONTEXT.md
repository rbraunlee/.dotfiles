# Glossary — agent-assisted delivery workflow

These terms distinguish the [locally accepted first one-slice trial](archive/calculator-s0-2026-10-06.md)
(S0) and its [workflow plan](workflow-plan.md) from
the [longer-term aligned target](alignment.md). Legacy loop analysis is retained
on `experiment/opencode-routine-w1-w2-checkpoint` at
`linux/opencode-routine/docs/workflow/loop-logic.md`, not in the current root set.

**Current scope (2026-10-06):** S0 is a trusted-local, independently cloned single
slice with human-controlled publication and final merge. Sandboxing is deferred to
a separate project; neither a clone nor role permissions provide isolation. The
launcher, Coordinator, multiple slices, PR lifecycle and durable state below are
longer-term concepts, not preconditions or accomplishments of S0.

## Product and planning

- **Feature**: A coherent product outcome reviewed and accepted as a whole.
- **Feature spec**: The authoritative description of a feature's intended behavior,
  acceptance criteria, constraints, testing expectations and exclusions.
- **Slice**: A bounded, independently verifiable contribution to a feature,
  normally expressing thin end-to-end behavior.
- **Slice ticket**: The description of a slice's work, applicable requirements,
  constraints, verification expectations and dependencies.
- **Slice graph**: The slices of a feature and their dependency relationships.
- **Approved planning package**: The feature spec and slice graph reviewed by the
  user and authorized as the basis for execution.
- **Shared contract**: An agreed interface or behavior relied on by multiple slices.
- **Contract-owning slice**: The single slice responsible for an agreed change to
  a shared contract.
- **Consumer slice**: A slice relying on a shared contract owned or changed by
  another slice.
- **Dependency-ready slice**: A slice whose required prerequisites are satisfied.
- **S0 trial**: One approved, bounded dependency-ready slice of a feature, tested
  in an independent clone and verified again as a disposable combined candidate.
  It is a workflow proof, not an accepted feature or launcher qualification.

## Execution and review

- **Trusted local execution**: Approved agent and project commands running on the
  host without sandbox security containment. Separate directories and role controls
  do not isolate host files, credentials, networks, processes or resources.
- **Slice clone**: An independent Git repository in a slice-specific directory,
  with its own branch and Git metadata, without shared alternates. The slice's
  Orchestrator/subagents/tools operate there from a recorded feature baseline.
- **Feature baseline**: The exact approved commit/ref from which the slice clone
  starts; changes to the expected feature head block publication until reviewed.
- **Disposable candidate**: A separately prepared combination of the final slice
  and recorded feature state. Required integration checks run on its exact commit;
  a passing slice alone does not establish that the candidate passes.
- **Host launcher**: The deterministic workflow component managing claims/state,
  local clone/session lifecycle, artifact collection, PR operations and gated
  integration. Experimental W1/W2 work is checkpointed on a separate branch;
  the launcher is not required for S0. It is infrastructure, not another AI coordinator.
- **Coordinator**: The role responsible for scheduling a feature's approved work
  and managing its slice PR and integration lifecycle in the longer-term target.
- **Slice Orchestrator**: The role responsible for one slice's implementation,
  independent verification/review, repairs and result handoff. In S0 this role
  creates the independent clone/branch and verifies the disposable candidate;
  other coordination may be manual.
- **Builder**: The role responsible for implementing a slice, including its tests,
  scoped refactoring and clean commits.
- **Tester**: The independent role that executes checks and assesses acceptance
  coverage without changing the product or committed tests.
- **Reviewer**: A fresh read-only role that assesses the final slice change
  against approved requirements and applicable standards, independently of Tester.
- **Explore**: The helper role for local codebase discovery.
- **Research**: The helper role for external technical evidence and cited findings.
- **Recaper**: The optional interactive role explaining a finished feature's
  structure and behavior.
- **Project setup**: The onboarding process that establishes a project's approved
  execution environment and verification expectations.
- **Project readiness**: A project's suitability for executing work under the
  agreed environment, checks and constraints.
- **Run**: An identifiable execution of work with recorded inputs and outcomes.
- **Repair attempt**: A corrective Builder pass addressing failed checks or
  blocking review findings. S0 allows at most two after initial implementation;
  affected checks and review repeat on the final commit.
- **Blocking finding**: An unmet requirement or concrete defect/risk that prevents
  integration.
- **Advisory finding**: A non-required improvement or preference that does not
  prevent integration.
- **Provisional output**: Completed work held out of integration pending resolution
  of an affected conflict or contract disagreement.
- **Reconciliation slice**: Corrective work combining affected slice outputs to
  resolve implementation conflicts while preserving approved contracts.
- **Completion correction**: Corrective work addressing approved feature
  requirements omitted by the original slice decomposition.

## Integration and acceptance

- **Feature integration branch**: The branch assembling the verified contributions
  of a feature before its final acceptance.
- **Integration candidate**: The combined result under verification before it
  becomes the published feature state. S0 prepares and checks one disposable
  candidate without automatically advancing the feature head.
- **Slice PR**: The review and traceability record for a slice's contribution.
- **Final feature PR**: The review and acceptance record for the integrated feature
  proposed for `main`.
- **Ready for integration**: A slice outcome eligible for host-controlled gating,
  not evidence that integration or human acceptance has already occurred.
- **QA-ready**: A verified integrated feature ready for human inspection, with
  references, a checklist and a way to start its testing environment.
- **QA environment**: The later user-started runtime for testing a particular
  verified feature state, with explicit start/status/stop controls and no implied
  sandbox. It is not required for S0's candidate handoff.
- **QA sandbox**: The historical container-isolated QA model, deferred with the
  separate sandbox project; not a requirement of the current workflow.
- **Human QA**: The user's assessment of intent, usability and the finished outcome,
  distinct from automated checks and independent code review.
