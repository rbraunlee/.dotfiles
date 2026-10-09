---
name: setup-matt-pocock-skills
description: "Configure tracker, domain docs, local feedback loops, branch/runtime policy and QA once per repository."
---

# One-time project setup

OpenCode adaptation of the pinned upstream setup pattern; see `../../workflow/UPSTREAM.md`.
This is a prompt-driven skill, not an installer or deterministic launcher.

1. Read existing `AGENTS.md`/`CLAUDE.md`, `docs/agents/`, domain docs, package scripts,
   Makefile/CI, README and Git conventions. Preserve existing configuration. If
   setup is already complete, consume it without repeating the setup interview.
   Do not read secret values, environment files or credential stores.
2. Summarize discoveries and ask only unresolved choices. **Local Markdown** is
   the default tracker even with a hosted remote; GitHub, GitLab or another tracker
   can be selected. Record read/create/update/close operations and what completion
   means in `docs/agents/issue-tracker.md`, using the adjacent templates as seeds.
   Labels are optional unless the selected workflow needs them. Do not provision
   hosted labels, issues or PRs without the project's explicit authorization.
3. Record existing glossary/map and ADR paths in `docs/agents/domain.md`. Prefer
   existing `CONTEXT.md` conventions over creating a parallel `GLOSSARY.md`. Create
   glossary/ADRs lazily when a term/decision is resolved, never as setup ceremony.
4. Discover exact setup, test, lint, type-check and build commands with their
   working directories. Record them and baseline results in
   `docs/agents/project.md`, starting from [project.md](project.md). Mark a check
   inapplicable only with a rationale; missing required feedback loops are explicit
   setup work, not permission to silently start delivery. Confirm routine local
   commands work, including required development service setup.
5. Record branch/commit conventions, approved worktree root, concurrency (default
   two), development-only access, shared ports/databases/generated paths, safe
   namespacing or serialization, integration/final checks and QA run instructions.
   No production access or deployment is authorized. Worktrees are not sandboxes.
6. Record publication policy: local-only by default, or explicitly authorized
   feature-branch pushes and **one feature PR** to a named host/repository. Never
   authorize automatic `main` merge. Record preview policy (off unless requested).
   External-directory access stays permission-controlled; don't grant broad access
   merely to silence prompts. Normal local delivery uses native V2 `permissions:`.
7. Present the setup draft for confirmation, then write only the agreed documents.
   Add/update a short `## Agent skills` pointer block in the existing instruction
   file; prefer `AGENTS.md` when neither exists. Preserve all surrounding user
   instructions. Include tracker, domain and project profile pointers. Configured
   documentation outside allowed paths requires a narrow permission, not an
   application-source edit loophole.
8. Report setup ready only when required baseline checks succeed. Otherwise list
   concrete setup blockers. Subsequent features read this profile; rerun setup
   only to change the project workflow or repair an observed missing requirement.
