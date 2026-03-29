# Created by Zap installer
[ -f "${XDG_DATA_HOME:-$HOME/.local/share}/zap/zap.zsh" ] && source "${XDG_DATA_HOME:-$HOME/.local/share}/zap/zap.zsh"
plug "zsh-users/zsh-autosuggestions"
plug "zap-zsh/supercharge"
plug "zsh-users/zsh-syntax-highlighting"

eval "$(starship init zsh)"
# Load and initialise completion system
autoload -Uz compinit
compinit

export PATH="$(brew --prefix ruby)/bin:/opt/python@3.12/libexec/bin:/opt/homebrew/opt/openjdk@11/bin:$PATH"
export JEKYLL_EDITOR=nvim

alias vim="nvim"

autoload -Uz compinit && compinit
zstyle ':completion:*' matcher-list 'm:{a-z}={A-Za-z}'

export GPG_TTY=$(tty)



# Generated for envman. Do not edit.
[ -s "$HOME/.config/envman/load.sh" ] && source "$HOME/.config/envman/load.sh"
