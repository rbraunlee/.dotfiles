# Experimental history index (2026-10-06)

This branch checkpoints the earlier launcher and sandbox work; it is **not** the active S0 plan. The active one-slice plan is `docs/workflow-plan.md` on `main`. No real W2 qualification or new sandbox trial was run for this checkpoint. Earlier root `docs/` originals remain local, ignored and unchanged. Each historical copy retains its dated claims and an origin banner; references to `docs/...` inside a copy refer to the original drafting layout, not to a current root document on this branch.

| Original root document | Copy on this branch | Status |
| --- | --- | --- |
| `docs/implementation-plan.md` | [workflow/implementation-plan.md](workflow/implementation-plan.md) | W1–W9 implementation sequence superseded as the active order; W1 accepted, W2 assembled, not real-qualified |
| `docs/loop-logic.md` | [workflow/loop-logic.md](workflow/loop-logic.md) | Legacy multi-slice loop analysis |
| `docs/brainstorming.md` | [workflow/brainstorming.md](workflow/brainstorming.md) | Mixed decision and exploration history, not current S0 instructions |
| `docs/plan-change-proposal.md` | [workflow/plan-change-proposal.md](workflow/plan-change-proposal.md) | Dated proposal; later approval was recorded separately, old cleanup snapshot superseded |
| `docs/review-findings-2026-10-05.md` | [workflow/review-findings-2026-10-05.md](workflow/review-findings-2026-10-05.md) | Dated findings, including now-fixed agent regression; counts are historical |
| `docs/archive/implementation-plan-sandbox-2026-10-04.md` | [sandbox/implementation-plan-sandbox-2026-10-04.md](sandbox/implementation-plan-sandbox-2026-10-04.md) | Earlier M1/M2 plan; sandbox gates deferred for S0, not passed or waived for future sandbox work |
| `docs/m2-interface-checkpoint.md` | [sandbox/m2-interface-checkpoint.md](sandbox/m2-interface-checkpoint.md) | Offline interface checkpoint |
| `docs/m2-network-proposal.md` | [sandbox/m2-network-proposal.md](sandbox/m2-network-proposal.md) | Deferred network proposal |
| `docs/m2-services-proposal.md` | [sandbox/m2-services-proposal.md](sandbox/m2-services-proposal.md) | Deferred services proposal |
| `docs/m2-storage-proposal.md` | [sandbox/m2-storage-proposal.md](sandbox/m2-storage-proposal.md) | Deferred storage proposal; host procedures are not authorized |
| `docs/m2-qualification.md` | [sandbox/m2-qualification.md](sandbox/m2-qualification.md) | Dated sandbox evidence, unresolved gates; host paths and retained private logs are not a new approval |

Root `docs/sandcastle-investigation.md` and `docs/skills-ranking.md` are unrelated research notes: they remain local, ignored and unclassified rather than being copied here. The root `docs/alignment.md` and `docs/CONTEXT.md` are current documents to be revised on `main`, not package history.

## Checkpoint verification

From the repository root, with `OPENCODE_ROUTINE_TEST_IMAGE`, `OPENCODE_ROUTINE_COMPONENT_IMAGE` and `OPENCODE_ROUTINE_STORAGE_IMAGE` explicitly unset, `TMPDIR=/tmp/opencode PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s linux/opencode-routine/tests -v` ran **601 tests: 582 passed, 19 skipped** on 2026-10-06. Eighteen skips require explicitly approved live images/Docker access; one tagged-input test skipped because retained input bytes were unavailable. This is offline regression coverage, not real W2 OpenCode session/delegation/owned-descendant qualification and not a sandbox acceptance claim.
