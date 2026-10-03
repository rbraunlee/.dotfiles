# Cursor skills

Skills for Cursor/Composer. **This package no longer ships agents** — see
[Agents](#agents) below.

## Install

From the dotfiles root:

```bash
stow -d common -t ~ cursor
```

To remove:

```bash
stow -D -d common -t ~ cursor
```

**Note:** If `~/.cursor/skills` already exists as a real directory with other
content, stow will conflict. Resolve before installing.

## Skills

| Skill | Purpose |
|-------|---------|
| `brainstorm` | Structured ideation session using proven techniques |
| `grill-with-docs` | Stress-test a plan against the domain model and project language, updating `CONTEXT.md` and ADRs as decisions land |

`brainstorm` is the only Cursor-specific file here — its text differs from the
OpenCode copy. `grill-with-docs` is byte-identical to the OpenCode skill, so the
two copies can drift apart at any time.

## Agents

The nine agents that used to live in `.cursor/agents/` were removed as duplicated
drift. Each had drifted from its twin in
[common/opencode](../opencode/.config/opencode/agents/) — same names, different
prompts — and nothing kept the two trees in step:

| Was | Also in OpenCode |
|-----|-----------------|
| `aligner` | yes |
| `brainstomer` | yes |
| `builder` | yes |
| `cleaner` | yes |
| `orchestrator` | yes |
| `planner` | yes |
| `recaper` | yes |
| `refactorer` | yes |
| `tester` | yes |

OpenCode is the system of record for agents and has the fuller set — it also has
`tutor`, which Cursor never had. If you move back to Cursor, port them from
there rather than maintaining a second copy.

## Workspace artifacts

The workflow these agents participated in wrote to `docs/`, which is gitignored
and therefore not shared through this repo:

| File | Purpose |
|------|---------|
| `docs/brainstorming.md` | Phase 1 output |
| `docs/alignment.md` | Phase 2 output |
| `docs/plan.md` | Phase 3 output — single source of truth for execution |
| `current-slice.toml` | Orchestrator resume state |

## Models

OpenCode agents set per-agent `model:` values; Cursor subagents inherit from the
Composer session instead. This package no longer has agents to carry that
difference.