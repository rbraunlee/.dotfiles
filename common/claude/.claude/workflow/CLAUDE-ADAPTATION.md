# Claude Code adaptation of the OpenCode workflow

Provenance for the vendored skills is in [UPSTREAM.md](UPSTREAM.md) (a link to the
OpenCode package's record). This file records how the `claude` package maps the
OpenCode workflow onto Claude Code. Updates are manual review work; never fetch or
auto-update skills during delivery.

## Shared versus adapted skills

Skills whose text is harness-neutral are **relative symlinks** into the OpenCode
package, so both harnesses read one copy: `brainstorm`, `codebase-design`,
`domain-modeling`, `grilling`, `import-notes`, `tdd`, `to-spec`, `to-tickets`, the
setup templates, the license and `upstream-lock.json`.

Adapted copies live in this package: `implement-spec` (and `LOCAL-EXECUTION.md`),
`implement`, `ship` (plus `worktree_in_use.py`), `setup-matt-pocock-skills`
(`SKILL.md`, `project.md`), `grill-with-docs` and `spec-review`, plus every agent.
[adapted-from.json](adapted-from.json) records the SHA-256 of each OpenCode source at
adaptation time; the package tests fail when a source changes, until the change is
ported here and the hash updated.

## Mapping

- **Skills and commands.** Claude Code skills are slash commands, so the seven thin
  OpenCode commands are not needed. `implement-spec`, `implement` and `ship` set
  `disable-model-invocation: true`: only the owner can kick off delivery or ship.
- **`code-review` is renamed `spec-review`** because Claude Code has a built-in
  `/code-review` command with different behaviour.
- **Primary agents** (`planner`, `orchestrator`, `shipper`) are agent files run as
  the main session with `claude --agent <name>`. The delivery skills also work in a
  plain session by adopting the agent file, with weaker hook enforcement because the
  hook keys on `agent_type`.
- **Subagents** keep their names and contracts. `disallowedTools` removes `Agent`
  (no nesting) and edit tools for read-only roles; MCP tools stay inherited.
- **Models.** `gpt-6.1-sol` roles map to `opus`, `gpt-6-sol` (builder, tester) to
  `sonnet`, `gpt-5.3-codex-spark` (cleaner, refactorer) to `haiku`, keeping each
  role's effort where the model supports it.
- **Permissions.** Claude Code rules are unordered (deny beats ask beats allow) and
  global. Rules that need ordering, a role or the current branch live in
  `hooks/policy.py`: branch-aware `main` protection, per-role shell/edit/agent
  limits, primary-checkout refusal for delivery roles, the `.env.example`
  exception and draw.io scoping. Settings keep the unordered rules (secret reads,
  destructive-command asks, `gh pr merge` deny, `/etc` deny).
- **Routing.** OpenCode's `session_move` has no Claude Code equivalent: subagents
  never keep a `cd`, and `EnterWorktree` cannot move a subagent out of the main
  checkout (verified on v2.1.310). Children prefix every Bash call with
  `cd '<worktree>' && ` and use absolute paths; the hook refuses delivery-role
  commands and edits in a primary checkout. Worktrees default to
  `~/.local/share/claude-worktrees/<project>/`, an additional working directory in
  user settings, and are created with `git worktree add` at exact SHAs rather than
  with Claude Code's own worktree isolation.
- **Evidence and sessions.** Child evidence comes from `SendMessage` to the same
  agent or its transcript under `~/.claude/projects/`. The `/ship` in-use check uses
  live Claude Code session files and `lsof` instead of `opencode session list`.
- **Attribution.** Delivery commits use `Claude Agent <claude-agent@users.invalid>`
  and an `Agent: Claude Code / <model ID>` trailer; Claude Code's own
  `Co-Authored-By` trailer may also appear.
- **MCP.** User-scope servers live in `~/.claude.json`, which Claude Code owns, so
  `mcp/install.sh` registers them instead of stowing a config file.
- **Not carried over:** OpenCode's tool-output caps, file watcher and TUI settings,
  and the reviewer's OpenCode permission-audit procedure.
