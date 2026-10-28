# dotfiles

Managed with [GNU Stow](https://www.gnu.org/software/stow/).

## Prerequisites

- Git and GNU Stow
- The applications for your selected packages (see [package inventory](PACKAGES.md))
- Node.js/npm only for optional MCP integrations
- [Nerd Font](https://www.nerdfonts.com/) (e.g. Comic Shanns Mono)

## Structure

```
.dotfiles/
  common/   # cross-platform packages
  linux/    # linux-only packages
  macos/    # macos-only packages
```

Each subdirectory is a stow package that mirrors `$HOME`.

## Usage

Clone into your home directory and `cd` into it:

```bash
git clone <repo-url> ~/.dotfiles
cd ~/.dotfiles
```

### Post-clone git setup

Two settings are **local git config**, so they are not committed and must be run
once in every new clone:

```bash
git config core.hooksPath .githooks   # enable the commit-msg hook
git config merge.ff only              # refuse merge commits on main
```

Without the first line the hook sits in `.githooks/` unused — git never runs a
hook just because the file exists. Verified: in a fresh clone with
`core.hooksPath` unset, `git commit -m "changes"` succeeds.

Both are trivial to undo:

```bash
git config --unset core.hooksPath
git config --unset merge.ff
```

### Commit conventions

`.githooks/commit-msg` enforces [Conventional Commits](https://www.conventionalcommits.org/)
on the **first line only**:

```
<type>(<scope>): <subject>
```

| Type | For |
|---|---|
| `feat` | A new capability |
| `fix` | Correcting broken behaviour |
| `docs` | Comments and documentation only |
| `refactor` | Restructuring, no behaviour change |
| `perf` | Measurably faster or smaller |
| `chore` | Tooling, ignore rules, dependencies |
| `style` `test` `build` `ci` `revert` | Also accepted; rarely needed here |

The scope is optional and names the stow package. Several may be listed:

```
fix(nvim): port treesitter spec to the main branch API
fix(zsh,hypr): replace hardcoded /home/rbl paths with $HOME
feat: messages with no scope are fine too
```

Subjects should be imperative mood ("repair", not "repaired"), no trailing
period, under 100 characters.

`Merge ` and `Revert ` messages pass automatically — git writes those and they
cannot be reworded. Anything else can bypass with `--no-verify`.

**The hook only checks line one.** Bodies and footers are not enforced, and they
are where most of the value is:

```
fix(nvim): port treesitter spec to the main branch API

nvim-treesitter's frozen master branch does not support Neovim 0.12. The main
branch does, and needs tree-sitter-cli 0.26.1+ — the 0.25 figure in the master
README is wrong for that branch.
```

`merge.ff only` means `git merge` will refuse when branches have diverged and
suggest a rebase instead of leaving a merge commit on `main`.

### Stow packages

Dry run first to check for conflicts:

```bash
stow -n -v --no-folding -t ~ -d common nvim zsh ghostty tmux starship wallpaper
```

Apply for real (drop `-n -v`):

```bash
stow --no-folding -t ~ -d common nvim zsh ghostty tmux starship wallpaper
```

Platform-specific:

```bash
# linux: select packages for your desktop; inspect existing configs first
stow -n -v --no-folding -t ~ -d linux hypr swappy waybar wofi zsh
# Optional dictation config and user service; read linux/voxtype/README.md first
stow -n -v --no-folding -t ~ -d linux voxtype

# macos
stow -n -v --no-folding -t ~ -d macos aerospace
```

Drop `-n -v` only after reviewing conflicts. These commands link files; they do
not install applications, reload the desktop or enable services. The legacy Bash
package is opt-in. See [all packages and optional agent setup](PACKAGES.md).

### Unstow

```bash
stow -D --no-folding -t ~ -d common nvim
```

### Restow (clean re-link)

```bash
stow -R --no-folding -t ~ -d common nvim
```

## Notes

### Repository checks

Run all package suites, including OpenCode's package-local tests:

```bash
python3 -B tests/run.py
```

See [test prerequisites and coverage](tests/README.md) for native dependencies,
suite selection, optional-tool skips and checks that require a live desktop.

### Codex feature delivery

The `codex` and `agent-skills` packages provide Codex configuration, three focused
child roles and the adapted planning/delivery skills. Install them separately with
`--no-folding` so runtime state stays outside the dotfiles checkout:

```bash
stow -n -v --no-folding -t ~ -d common codex agent-skills
stow --no-folding -t ~ -d common codex agent-skills
```

See [Codex setup](common/codex/README.md) for usage, optional MCP integrations,
CLI/T3 execution differences and validation. OpenCode remains independently usable.

### OpenCode feature delivery

The `opencode` package provides skill-driven planning and trusted-local feature
delivery. Start with `/setup-matt-pocock-skills` once per project, then use
`/implement` for a bounded change or `/implement-spec <approved-spec>` for a ticket
graph. Agents leave
final QA and the merge into `main` to you; worktrees are not security sandboxes.

Run the package's configuration regression checks from the repository root:

```bash
python3 -m unittest discover -s common/opencode/.config/opencode/tests -v
```

Optional local MCP dependencies are installed after stowing with:

```bash
npm ci --prefix "$HOME/.config/opencode"
```

See [dependency maintenance](DEPENDENCIES.md) for lockfiles and intentional updates.

Runtime checks require OpenCode and the `opencode` package to be stowed. The checks
make no model calls and do not mutate project files.

### Claude Code feature delivery

The `claude` package ports the OpenCode workflow to Claude Code: the same roles and
skills, an owner-only `/ship` to `main`, and a policy hook for the rules Claude
Code's permission settings cannot express. Its unchanged skills link into the
`opencode` package, so keep both in the checkout:

```bash
stow -n -v -t ~ -d common claude
stow -t ~ -d common claude
```

See [Claude Code setup](common/claude/README.md) for usage, MCP registration and
limits. Run its checks with `python3 -m unittest discover -s tests/common/claude -v`.

### Nerd Fonts

**macOS:** `brew install font-comic-shanns-mono-nerd-font`

**Arch Linux:** `yay -S nerd-fonts-comic-shanns-mono`

### tmux plugins

TPM manages plugins under `~/.tmux/plugins`, outside the Stow checkout.
See [tmux installation and migration](common/tmux/README.md) for bootstrap,
reload, persistence and verification instructions.
