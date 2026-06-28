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

### Nerd Fonts

**macOS:** `brew install font-comic-shanns-mono-nerd-font`

**Arch Linux:** `yay -S nerd-fonts-comic-shanns-mono`

### tmux plugins

```bash
git clone https://github.com/tmux-plugins/tpm ~/.tmux/plugins/tpm
```

Open tmux and press `prefix + I` to install plugins.


