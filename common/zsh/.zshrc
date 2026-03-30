# --- 1. Zap Plugin Manager ---
if [ -f "${XDG_DATA_HOME:-$HOME/.local/share}/zap/zap.zsh" ]; then
    source "${XDG_DATA_HOME:-$HOME/.local/share}/zap/zap.zsh"
    plug "zsh-users/zsh-autosuggestions"
    plug "zap-zsh/supercharge"
    plug "zsh-users/zsh-syntax-highlighting"
fi

if command -v starship >/dev/null 2>&1; then
    eval "$(starship init zsh)"
fi

# --- 2. Shared Environment ---
eval "$(starship init zsh)"
autoload -Uz compinit && compinit
zstyle ':completion:*' matcher-list 'm:{a-z}={A-Za-z}'

alias v="nvim"
alias vim="nvim"
export GPG_TTY=$(tty)

# --- 3. OS-Specific Conditional Logic ---
if [[ "$OSTYPE" == "darwin"* ]]; then
    # --- macOS Paths ---
    if command -v brew >/dev/null 2>&1; then
        export PATH="$(brew --prefix ruby)/bin:/opt/homebrew/opt/openjdk@11/bin:$PATH"
    fi
    export PATH="/opt/python@3.12/libexec/bin:$PATH"
    
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # --- Arch/Linux Configs ---
    alias pacman="sudo pacman"
    export MOZ_ENABLE_WAYLAND=1
fi

# --- 4. External Loaders ---
[ -s "$HOME/.config/envman/load.sh" ] && source "$HOME/.config/envman/load.sh"
