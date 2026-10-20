# Reviewed skill snapshot

- Source: https://github.com/mattpocock/skills
- Exact commit: `b0618bc436ad893b3c5e84e55fba86586d34a404`
- Retrieved/reviewed: 2026-10-08
- License: [MIT](../skills/MATT-POCOCK-LICENSE.txt), copyright 2026 Matt Pocock
- Original source paths and SHA-256 hashes: [upstream-lock.json](../skills/upstream-lock.json)
- Updates are manual review work. Never fetch or auto-update skills during delivery.

Vendored `setup-matt-pocock-skills`, `grill-with-docs`, `to-spec`, `to-tickets`,
`implement`, `implement-spec`, `tdd`, `code-review`, and dependency closure:
`grilling`, `domain-modeling` (including glossary/ADR formats), `codebase-design`
(including deepening/design references), TDD test/mocking references and setup
tracker/domain templates. Upstream `agents/openai.yaml` files are intentionally
omitted: they are another harness's UI metadata, not OpenCode agent contracts.

## OpenCode adaptations

- Entry skills are discoverable by `id` and callable through thin slash commands.
  Existing local `grill-with-docs` is replaced by the pinned composable wrapper,
  respecting configured `CONTEXT.md`/glossary paths rather than requiring a rename.
- Setup defaults to local Markdown, preserves configured domain layout, and adds
  project feedback loops, baseline validation, worktree/runtime, publication and
  human QA policy (`setup-matt-pocock-skills/project.md`). No hosted label ceremony.
- `to-spec` reuses the current planning context/seams, records explicit acceptance
  and approval, and doesn't invent a long story list. `to-tickets` maps full-spec
  coverage, stable edges, risks/checks and approval; neither starts delivery.
- `implement` is the bounded fast path. `implement-spec` keeps the upstream
  frontier/worktree/Merger structure but adds verified **OpenCode Location** routing,
  project profile, serialized exact-SHA integration, safe cleanup and recovery.
  No reset-on-mismatch, Implementer merging, unconditional worktree deletion,
  draft PR before verification, custom launcher or ledger. Shared operational
  procedure lives in `implement-spec/LOCAL-EXECUTION.md`.
- Full-feature independent Tester and fresh Reviewer gate the immutable final
  commit. At most two repair passes; user owns QA/`main` merge. One authorized
  feature PR or local handoff; no routine ticket PRs or intermediate approval gates.
  Later: owner-invoked `/ship` after QA is now the agent path to `main` (see the
  2026-10-20 entry) and creates the one feature PR in `pr` mode.
- `code-review` retains independent Spec/Standards axes and the smell baseline but
  the fresh Reviewer performs both directly with read-only Git. No nested review
  agents, copied diff, three-dot-only gate or spec-axis skip. Explicit supplied
  spec/fast-path acceptance takes precedence over unrelated repository planning files.
- TDD reuses pre-approved seams instead of requesting human confirmation for each
  ticket and consumes configured glossary/ADR paths. Domain modeling honors configured
  paths; grilling uses in-context fact
  discovery with optional rather than mandatory delegation.
- MVP-focused planning adaptation (2026-10-13): the primary planner proposes a
  purpose-preserving complete workflow and justified cuts, with optional exploration
  and selective grilling rather than exhaustive design-tree interviews. `to-spec`
  separates current acceptance from vision and deferred possibilities; `to-tickets`
  decomposes only current approved scope when useful and respects configured tracker
  paths. The local `brainstorm` skill now reuses conversation context and follows
  requested depth; it is not a vendored upstream skill. These are prompt guidance,
  not a guarantee of model behavior or a change to execution/permission contracts.
- Owner-invoked ship adaptation (2026-10-20): the local `ship` skill, `/ship`
  command and primary `shipper` agent end delivery after human QA. Read-only
  pre-flight (recorded tested/reviewed SHA equals the feature tip, clean feature and
  primary `main` checkouts), explicit owner QA approval, then either one attributed
  `git merge --no-ff` into `main` (abort on conflict, never push) or one feature PR,
  followed by retirement (copy/verify records, non-force worktree removal,
  `git branch -d`). Setup records `Ship mode: local-merge | pr`; delivery handoffs
  end with "after human QA, run `/ship <feature>`"; `implement-spec` deletes merged
  ticket branches with `git branch -d` instead of retaining them. Permission
  patterns match command text, not the current branch, so they cannot enforce
  "only `/ship` merges `main`"; the Merger keeps its feature-branch merges.
- Supporting references not listed above are unchanged; originals can be recovered
  from the pinned commit and validated against the lock's original hashes. The
  local `brainstorm`, `import-notes` and `ship` skills are not from this snapshot.

`UPSTREAM.md` is provenance, not an executable skill. No unreviewed upstream
scripts, installation commands or auto-updaters are included.
