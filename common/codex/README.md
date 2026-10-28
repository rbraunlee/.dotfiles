# Codex setup

Two independent GNU Stow packages:

- `codex`: `~/.codex/config.toml`, three custom agents, an optional MCP profile,
  and pinned MCP dependency declarations under `~/.local/share/codex-mcp`.
- `agent-skills`: portable skills under `~/.agents/skills`, including their
  references, templates, upstream hashes and license.

OpenCode keeps its existing configuration and reviewed snapshot. Do not install
both copies into the same skill discovery directory. Review upstream updates
manually; the provenance records describe originals, not adapted-file hashes.

## Install

From the repository root, review the dry run before applying:

```sh
stow -n -v --no-folding -t ~ -d common codex agent-skills
stow --no-folding -t ~ -d common codex agent-skills
```

`--no-folding` keeps runtime directories real: authentication, sessions, caches and
MCP node_modules must not be created inside the dotfiles checkout. Existing real
config/agent files can conflict; reconcile them manually rather than using
`--adopt`, which can overwrite the repository copy. Nothing here installs login
credentials or modifies the existing OpenCode package. Restart the client after
installation and check that the skills and agents are discoverable.

Base settings use workspace-write, on-request approvals and live web search.
Models/reasoning inherit from the client rather than pinning account-specific IDs.
The three roles are builder, tester and reviewer. Their instructions do not grant
separate permissions: custom agents inherit the parent's sandbox. T3 can override
configuration and provides its own delegation lifecycle; inspect effective settings.
No OpenCode glob-based secret or branch policy is claimed to transfer. Environment
secret-name filtering reduces accidental inheritance; it is not file containment.

## Use

- `$setup-matt-pocock-skills`: establish project checks, tracker/domain paths,
  runtime policy, protected branch and shipping mode.
- `$brainstorm`, `$grill-with-docs`, `$to-spec`, `$to-tickets`: plan at the depth
  needed. A bounded change needs no ticket graph.
- `$implement`: direct work and proportionate checks for small changes; isolated
  work and independent verification for substantial/risky changes.
- `$implement-spec`: dependency-ready workers, serialized coordinator integration,
  independent final Tester and fresh Reviewer at the same SHA.
- `$ship <feature>`: explicit-only shipping after human QA. Reuses explicit QA
  approval already supplied for the same feature/SHA. Local merge or one feature
  PR follows project policy; protected branches are never pushed automatically.
- `$tutor`, `$recap`, `$import-notes`: optional interactive workflows.

The delivery contract is in
`~/.agents/skills/implement-spec/LOCAL-EXECUTION.md`. Its CLI and T3 references keep
host-specific workspace binding separate. T3 children receive explicit role briefs;
do not assume it loads the standalone CLI agent definitions. Worktrees are Git
organization, not host isolation. Required gates cannot be waived by using the
small-change path. Self-checks must be reported as such.

## Optional integrations

After stowing with `--no-folding`, install the pinned top-level dependencies:

```sh
npm ci --prefix "$HOME/.local/share/codex-mcp"
codex --profile integrations
```

The committed lockfile pins transitive dependencies; `node_modules` stays
machine-local. See [dependency maintenance](../../DEPENDENCIES.md) for updates.
The profile enables Obsidian, Brave and draw.io.
Supply `OBS_MCP_TOKEN` and `BRAVE_SEARCH_TOKEN` through your existing secret manager
or private process environment, never committed files. The Brave launcher maps the
existing token name to the server's `BRAVE_API_KEY`. Obsidian requires the local
HTTPS service and a trusted certificate. Do not disable TLS verification to connect.
If you need only one integration, enable only its table in a private profile.
Native web search works without Brave. No MCP service is contacted by default.

## Validate

```sh
python3 -m unittest discover -s tests/common/codex -v
```

The tests check TOML/frontmatter/reference integrity, isolated Stow install/restow/
unstow with runtime files preserved, and strict startup-config validation with the
installed CLI when available. They make no model calls or MCP connections.
Skill decisions, delegated workspace routing, real server authentication and
end-to-end shipping still require runtime exercise; prompt checks cannot prove
those behaviors. Baseline validated with Codex CLI 0.164.0.

References consulted for this port:
[skills](https://learn.chatgpt.com/docs/build-skills),
[agents](https://learn.chatgpt.com/docs/agent-configuration/subagents),
[configuration](https://learn.chatgpt.com/docs/config-file/config-reference).
