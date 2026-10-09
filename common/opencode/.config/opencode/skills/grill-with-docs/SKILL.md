---
name: grill-with-docs
description: "Stress-test a plan against domain language and record resolved glossary terms and ADRs in the same planning context."
---

Load `grilling` and `domain-modeling` with the native `skill` tool's `id` field.
Keep the interview and document updates in this primary planning session; optional
focused exploration is not a mandatory phase handoff. Resolve real ambiguity only.

Read `docs/agents/domain.md` first when present. Its configured glossary/map and
ADR locations override upstream `GLOSSARY.md` defaults, including existing
`CONTEXT.md` conventions. Never create a parallel glossary or overwrite existing
decisions. Use the supporting formats shipped with `domain-modeling`.

Once intent is settled, `to-spec` synthesizes the existing discussion and `to-tickets`
proposes the graph. Do not restart the interview. Approval is not implementation
kickoff. Provenance and this OpenCode adaptation are in `../../workflow/UPSTREAM.md`.
