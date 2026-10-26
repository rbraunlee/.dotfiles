---
name: grill-with-docs
description: "Stress-test a plan against domain language and record resolved glossary terms and ADRs in the same planning context."
---

Read `../grilling/SKILL.md` and `../domain-modeling/SKILL.md`.
Keep consequential questions and document updates in this primary planning session;
optional focused exploration is not a mandatory phase handoff. A clear bounded
request can need no interview. Honor explicit deeper stress tests. Resolve real
ambiguity only, preserving the usefulness of the proposed increment rather than
visiting every design branch.

Read `docs/agents/domain.md` first when present. Its configured glossary/map and
ADR locations override upstream `GLOSSARY.md` defaults, including existing
`CONTEXT.md` conventions. Never create a parallel glossary or overwrite existing
decisions. Use the supporting formats shipped with `domain-modeling`.

Once intent is settled, `to-spec` synthesizes the existing discussion; `to-tickets`
proposes a graph only when decomposition is useful. Do not restart the interview.
Approval is not implementation kickoff. Provenance and this Codex adaptation are
in `../UPSTREAM.md`.
