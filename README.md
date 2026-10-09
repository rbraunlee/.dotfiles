# dotfiles

Managed with [GNU Stow](https://www.gnu.org/software/stow/).

## Prerequisites

- stow
- npm
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
stow -n -v -t ~ -d common nvim zsh ghostty tmux starship cursor opencode wallpaper
```

Apply for real (drop `-n -v`):

```bash
stow -t ~ -d common nvim zsh ghostty tmux starship cursor opencode wallpaper
```

Platform-specific:

```bash
# linux
stow -t ~ -d linux bash hypr swappy waybar wofi zsh

# macos
stow -t ~ -d macos aerospace
```

### Unstow

```bash
stow -D -t ~ -d common nvim
```

### Restow (clean re-link)

```bash
stow -R -t ~ -d common nvim
```

## Notes

### OpenCode feature delivery

The `opencode` package provides skill-driven planning and trusted-local feature
delivery. Start with `/setup-matt-pocock-skills` once per project, then use
`/implement` for a bounded change or `/implement-spec <approved-spec>` for a ticket
graph. See [usage and verification status](docs/workflow-adoption.md). Agents leave
final QA and the merge into `main` to you; worktrees are not security sandboxes.

Run the package's configuration regression checks from the repository root:

```bash
python3 -m unittest discover -s common/opencode/.config/opencode/tests -v
```

Runtime checks require OpenCode and the `opencode` package to be stowed. The checks
make no model calls and do not mutate project files.

### Nerd Fonts

**macOS:** `brew install font-comic-shanns-mono-nerd-font`

**Arch Linux:** `yay -S nerd-fonts-comic-shanns-mono`

### tmux plugins

```bash
git clone https://github.com/tmux-plugins/tpm ~/.tmux/plugins/tpm
```

Open tmux and press `prefix + I` to install plugins.
