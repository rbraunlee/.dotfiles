# Claude Code package

Claude Code port of the `opencode` planning and delivery workflow: the same roles,
skills and owner-only path to `main`, mapped onto Claude Code agents, skills,
settings and a `PreToolUse` policy hook. How each OpenCode piece maps is recorded in
[`.claude/workflow/CLAUDE-ADAPTATION.md`](.claude/workflow/CLAUDE-ADAPTATION.md).

## Install

`~/.claude` already exists and holds credentials and sessions, so stow links the
package's entries into it rather than replacing it:

```bash
stow -n -v -t ~ -d common claude   # dry run
stow -t ~ -d common claude
```

The unchanged skills are symlinks into the `opencode` package, so keep both packages
in the checkout (stowing `opencode` is not required). Settings reload live; start a
new session to pick up agents and skills.

MCP servers are registered at user scope by a script, because Claude Code keeps them
in `~/.claude.json`, which it owns. Export `OBS_MCP_TOKEN` and `BRAVE_SEARCH_TOKEN`
in the shell that starts Claude Code, then run once:

```bash
~/.claude/mcp/install.sh
```

The Obsidian server uses a self-signed certificate on `127.0.0.1`. If it fails to
connect, point `NODE_EXTRA_CA_CERTS` at the plugin's certificate.

## Use

| Step | Command |
| --- | --- |
| Plan a feature | `claude --agent planner`, then `/setup-matt-pocock-skills` once per project |
| Deliver an approved spec | `claude --agent orchestrator`, then `/implement-spec <spec>` |
| Deliver a bounded change | `claude --agent orchestrator`, then `/implement <request>` |
| Ship after human QA | `claude --agent shipper` in the primary checkout, then `/ship <feature>` |

`/implement-spec`, `/implement` and `/ship` are owner-only: the model never invokes
them by itself. Optional specialists (`aligner`, `brainstormer`, `recaper`, `tutor`)
run either as `claude --agent <name>` or as subagents. Delivery worktrees live under
`~/.local/share/claude-worktrees/<project>/`.

## Guardrails

`hooks/policy.py` enforces what Claude Code's unordered permission rules cannot:

- `main` is branch-aware protected in every session. Switching to it, force-moving
  or deleting it, pushing it and `gh pr merge` are refused. Merging into it asks
  unless the session runs as `shipper`.
- Delivery roles (`builder`, `merger`, `tester`, `reviewer`, `cleaner`,
  `refactorer`) are refused commands and edits in a primary checkout. They must
  start every Bash call with `cd '<worktree>' &&`.
- Per-role shell, edit and subagent limits follow the OpenCode agent rules.
- `.env.*` files are blocked for file tools except `.env.example`, and draw.io is
  limited to the aligner and brainstormer.

These are guardrails for trusted local development, not a sandbox. Commands hidden
in scripts or `sh -c` are not inspected. Shell reads of `.env.*` variants are only
covered by the settings rules for exact secret names such as `.env`.

`/config` and `/model` write `~/.claude/settings.json`. If Claude Code replaces the
symlink with a plain file, `git status` stays clean but the live file diverges; check
with `ls -l ~/.claude/settings.json` and restow.

## Test

```bash
python3 -m unittest discover -s tests/common/claude -v
```

The tests use throwaway Git repositories and a temporary stow target. They make no
model calls and need no Claude Code installation.
