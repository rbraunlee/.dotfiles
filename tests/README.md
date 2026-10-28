# Repository checks

Run all suites from the repository root:

```sh
python3 -B tests/run.py
```

The runner discovers package suites under `tests/<platform>/<package>` and
includes the package-local OpenCode suite. Each suite runs in its own process
to avoid module-name collisions. Failures do not prevent later suites from
running; the final exit status is nonzero if any suite fails or discovers zero
tests. Verbose output includes individual skips and their reasons.

List suites or select a subset:

```sh
python3 -B tests/run.py --list
python3 -B tests/run.py common/nvim linux/waybar
```

Plain `unittest discover -s tests` does not recurse into these non-package
directories. Use the runner, or discover from a specific suite directory.
No manual creation of `/tmp/opencode` is needed. Fixtures use private temporary
directories and clean them up. OpenCode retains its ancestor-definition checks
and isolated HOME/environment; permission tests still use synthetic paths.

## Prerequisites and coverage

Use Python 3.11+ (TOML parsing uses `tomllib`). No third-party Python packages
are required. The complete suite currently targets Linux:

- Claude: Git; Stow for its installation test. No Claude CLI required.
- MCP dependency checks (`common/mcp`): Python and `/bin/sh`; lockfile validation
  and stubbed installer ordering run offline. Real `npm ci` validation is separate;
  see [dependency maintenance](../DEPENDENCIES.md).
- Package installation (`common/stow`): Git and Stow. Copies tracked and new
  non-ignored package files into a temporary checkout, preserving relative links;
  exercises all package lifecycles and combined Linux/macOS layouts. No app is
  launched, downloaded or reloaded. New packages must be added to its coverage map.
- Codex: Stow and Codex CLI for installation/startup checks; missing tools are
  reported as skips. Static package checks still run.
- Neovim: Neovim supporting `-l` and the configured APIs, Git, and ripgrep.
  See the Neovim package README for runtime versions.
- tmux: tmux and Stow; tests use private server sockets and temporary homes
  without TPM downloads or saved sessions.
- Zsh: `/usr/bin/zsh`, `/usr/bin/python3`, and standard Unix utilities. Package,
  media and system commands are replaced with fixture providers.
- Hyprland: Lua and standard Unix shell utilities; no live compositor required.
- Voxtype: Stow; no transcription model or running service required.
- Waybar: Bash and standard Unix utilities; update providers are fixture scripts.
- Wofi: a C compiler, `pkg-config`, and GTK 3 development headers/libraries.
- OpenCode: Git; OpenCode V2 for runtime discovery. Missing OpenCode skips runtime
  tests. The private server makes no model calls and uses fixture configuration.

Missing required native tools fail the relevant suite; optional-tool skips mean
that coverage was not exercised. A passing run with skips is not full validation.
The runner installs nothing and does not reload the desktop or stow into your
real home. Visual behavior, real plugins, audio/transcription, session restore
and macOS behavior need separate validation on the relevant system.
