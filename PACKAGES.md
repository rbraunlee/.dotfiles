# Package inventory

All packages require Git and GNU Stow. Stow links configuration; it does not
install applications, download models, register integrations or start services.
Install only the packages you use. From the repository root, substitute the group
and package name below:

```sh
stow -n -v --no-folding -t ~ -d <group> <package>
stow --no-folding -t ~ -d <group> <package>
```

Review the dry run first. Existing directories are fine; conflicting files need
reconciliation. Avoid `--adopt`, which can change repository contents. Use the same
`--no-folding` flag with `-R` to restow or `-D` to unstow. This keeps directories
real so applications can create runtime state outside the checkout.

`python3 -B tests/run.py common/stow` checks all 20 packages individually and in
combined common+Linux and common+macOS layouts, including conflicts, cross-package
links and preservation of synthetic runtime files. These are filesystem checks on
Linux; they do not prove native macOS or desktop behavior. The legacy Bash package
is included for link integrity, not endorsed for deployment.

## Common packages

- **`nvim`** — Neovim, Git, a compiler and the parser/language tooling listed in
  [its README](common/nvim/.config/nvim/README.md). Optional OpenCode terminal and
  Ollama integration require their own programs/services. Restart Neovim after
  changes. Check: `python3 -B tests/run.py common/nvim`, then native `:checkhealth`.
- **`zsh`** — Zsh; Neovim is the default editor. Zap and Starship are optional;
  helper-specific providers are listed in the [shortcut reference](common/zsh/README.md).
  Open a new shell or use `reload`; external profile loaders can run on reload.
  Check: `python3 -B tests/run.py common/zsh`. Native macOS paths remain unverified.
- **`tmux`** — tmux and Git; TPM downloads plugins separately. See
  [installation and persistence](common/tmux/README.md). Reload with
  `tmux source-file ~/.config/tmux/tmux.conf`. Check: `python3 -B tests/run.py common/tmux`.
- **`ghostty`** — Ghostty and the configured Comic Shanns Mono Nerd Font. Ships
  `.config/ghostty/config.ghostty`; confirm your installation loads that filename.
  Reload through Ghostty after confirming the loaded path. Coverage: Stow only;
  font/theme rendering and automatic config discovery need native verification.
- **`starship`** — Starship; the Zsh package initializes it when available.
  A new prompt picks up configuration changes. Coverage: Stow only; inspect a
  prompt in the actual shell and font.
- **`t3`** — T3 Code; a Gruvbox Material theme matching Ghostty. Publish it with
  `~/.t3/bin/t3 theme set ~/.config/t3/themes/gruvbox-material.json` after
  stowing, and again after edits. Fonts are set in T3's settings. See
  [T3 notes](common/t3/README.md). Coverage: Stow only; theme rendering is a
  manual check.
- **`wallpaper`** — PNG files under `~/Pictures/Wallpapers`; needs a wallpaper
  application to display them. Reapply using that application. Coverage: Stow
  only; monitor sizing and image selection are manual checks.
- **`cursor`** — Cursor with skills support. Contains skills, no agent roles.
  Reopen the client and check skill discovery after installation. See
  [Cursor notes](common/cursor/README.md). Coverage: Stow only.
- **`opencode`** — OpenCode V2; optional MCP servers require Node.js/npm and their
  external services/credentials. Restart the client and verify agent/skill
  discovery. Check: `python3 -B tests/run.py common/opencode`. Runtime tests use
  a private server and make no model calls. Independent workflow snapshot.
- **`codex`** — Codex; optional MCP integrations require Node.js/npm. Install
  alongside `agent-skills`, then restart the client. Check:
  `python3 -B tests/run.py common/codex`. See [Codex setup](common/codex/README.md)
  for configuration, optional integrations and T3 delegation differences.
- **`agent-skills`** — Portable skills for a compatible agent client; no separate
  daemon. Restart the client and check discovery. Installed with `codex` in the
  example below; integrity checks are in `common/codex`, link checks in `common/stow`.
- **`claude`** — Claude Code; Python 3 for its policy hook, Node.js/npm for optional
  MCP setup. Keep the `opencode` package in the checkout because unchanged skills
  link to it; stowing OpenCode is not required. Restart the client for agent/skill
  changes. Check: `python3 -B tests/run.py common/claude`. See
  [Claude setup](common/claude/README.md) before registering MCP servers.

Optional agent installs (choose the clients you use; dry-run first):

```sh
stow -n -v --no-folding -t ~ -d common codex agent-skills
stow -n -v --no-folding -t ~ -d common opencode
stow -n -v --no-folding -t ~ -d common claude
stow -n -v --no-folding -t ~ -d common cursor
```

## Linux packages

- **`hypr`** — Hyprland compatible with the tracked Lua config, Hypridle,
  Hyprlock, Hyprpaper and the configured desktop programs. Screenshot integration
  needs Flameshot and the Hyprland desktop portal; dictation uses `voxtype`.
  See [startup/shortcut notes](linux/hypr/.config/hypr/README.md). Review independent
  HOME edits before adoption. Reload only at a suitable desktop checkpoint;
  startup handlers require a later login. Check: `python3 -B tests/run.py linux/hypr`;
  locking, portal interaction and session startup still need live checks.
- **`waybar`** — Waybar on Hyprland, WirePlumber, Arch update-query tools
  (`checkupdates`, `paru`), and Ghostty for the update action. Restart Waybar through
  your session's normal mechanism. Check: `python3 -B tests/run.py linux/waybar`;
  visible modules and workspace switching require a running desktop.
- **`wofi`** — Wofi/GTK 3 on Wayland. Reopen the launcher after changing config.
  Check: `python3 -B tests/run.py linux/wofi`; native rendering is a separate check.
- **`swappy`** — Swappy and an image source such as Grim. Reopen Swappy after
  changes. Coverage: Stow only; test a synthetic screenshot manually.
- **`voxtype`** — The release-compatible Voxtype CUDA setup, local model, `wtype`,
  PipeWire audio and systemd user services described in the
  [adoption guide](linux/voxtype/README.md). Stow installs configuration plus a user
  unit; it does not enable/restart it. Follow that guide for an intentional service
  reload/restart and next-login check. Check: `python3 -B tests/run.py linux/voxtype`;
  audio, GPU and focused-field output need live verification.
- **`zsh`** — Zsh and `start-hyprland`; adds `.zprofile` for tty1 desktop startup.
  Complements `common/zsh`, which provides `.zshrc`. Takes effect on the next login.
  Coverage: Stow only; login startup needs session verification.
- **`bash`** — Legacy, opt-in Bash profile. Contains obsolete host-specific paths
  and remains outside the recommended install. Review before sourcing. Coverage:
  Stow integrity only, not shell behavior.

## macOS and archived configuration

- **`macos/aerospace`** — AeroSpace; ships `.config/aerospace/aerospace.toml`.
  Confirm configuration loading and reload through AeroSpace on macOS. Coverage:
  Stow integrity on Linux only; window management and login startup unverified here.
- **`unused/x11/qtile`** — Archived Qtile/X11 configuration, outside the supported
  Stow package groups. No installation or test command is promised.

See [test prerequisites](tests/README.md) for native test dependencies. See [dependency maintenance](DEPENDENCIES.md) for locked MCP installs. Optional
integration credentials and local models are never installed by these commands.
