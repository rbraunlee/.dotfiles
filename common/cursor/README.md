# Cursor agents (vertical-slice workflow)

Port of the OpenCode agent harness for Cursor/Composer. All agents use `model: inherit` (same model as the parent Composer session). Only `recaper` is `readonly: true`.

## Install

From the dotfiles root:

```bash
stow -d common -t ~ cursor
```

To remove:

```bash
stow -D -d common -t ~ cursor
```

**Note:** If `~/.cursor/agents` or `~/.cursor/skills` already exist as real directories with other content, stow will conflict. Resolve before installing.

## Workflow phases

| Phase | Agent | Invocation |
|-------|-------|------------|
| 1 Brainstorm | brainstomer | `/brainstomer` |
| 2 Align | aligner | `/aligner` (after `docs/brainstorming.md` exists) |
| 3 Plan | planner | `/planner` (after alignment is confirmed) |
| 0 Execute | orchestrator | `/orchestrator run the next slice` |

### Workspace artifacts

| File | Purpose |
|------|---------|
| `docs/brainstorming.md` | Phase 1 output |
| `docs/alignment.md` | Phase 2 output |
| `docs/plan.md` | Phase 3 output — single source of truth for execution |
| `current-slice.toml` | Orchestrator resume state |

### Execution subagents (dispatched by orchestrator)

| Agent | Role |
|-------|------|
| builder | Implement active slice |
| tester | Scaffold or verify tests |
| recaper | Summarize changes (read-only) |
| refactorer | Post-build cleanup refactor |
| cleaner | Atomic commits, purge scratch files |

## Models

Every agent frontmatter sets `model: inherit`. Pick your model once in the Composer UI; all subagents follow it.

## OpenCode parity

This package mirrors [common/opencode](../opencode/). Both can be stowed independently. OpenCode-specific features (per-agent temperature, bash approval modes, skill permissions) are not replicated — behavior is prompt-enforced in Cursor.
