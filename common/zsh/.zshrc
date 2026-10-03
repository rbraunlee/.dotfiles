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
autoload -Uz compinit && compinit
zstyle ':completion:*' matcher-list 'm:{a-z}={A-Za-z}'

alias v="nvim"
alias vim="nvim"
alias reload="source ~/.zshrc"

export GPG_TTY=$(tty)

# --- 3. OS-Specific Conditional Logic ---
if [[ "$OSTYPE" == "darwin"* ]]; then
    # --- macOS Paths ---
    # This whole branch is inert on Linux; it only runs on macOS. Unverified
    # there — it cannot be tested from a Linux host.
    #
    # TODO: openjdk@11 was removed from Homebrew, so /opt/homebrew/opt/openjdk@11
    # cannot resolve on any current install. If you still want a JDK, use
    # $(brew --prefix temurin)/bin — temurin is the maintained OpenJDK formula.
    # Note /opt/homebrew is the Apple Silicon prefix (Intel is /usr/local), so
    # this hardcoded path only works on an ARM Mac with a default install.
    if command -v brew >/dev/null 2>&1; then
        export PATH="$(brew --prefix ruby)/bin:/opt/homebrew/opt/openjdk@11/bin:$PATH"
    fi
    # TODO: this path is wrong twice over — it hardcodes the prefix instead of
    # asking brew, and Homebrew installs python to $(brew --prefix python@3.12)/bin,
    # never a libexec/bin subdirectory. It resolves on no machine at all. Also
    # note it sits outside the `command -v brew` guard above, so it prepends the
    # dead path even on a Mac with no Homebrew installed. If python is wanted,
    # move it inside the guard and derive it with brew --prefix.
    export PATH="/opt/python@3.12/libexec/bin:$PATH"
    
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # --- Arch/Linux Configs ---
    alias pacman="sudo pacman"
    export MOZ_ENABLE_WAYLAND=1
fi

# --- 4. External Loaders ---
if [ -f "$HOME/.env" ]; then
    source "$HOME/.env"
fi

# The next line updates PATH for the Google Cloud SDK.
if [ -f "${HOME}/google-cloud-sdk/path.zsh.inc" ]; then . "${HOME}/google-cloud-sdk/path.zsh.inc"; fi

# The next line enables shell command completion for gcloud.
if [ -f "${HOME}/google-cloud-sdk/completion.zsh.inc" ]; then . "${HOME}/google-cloud-sdk/completion.zsh.inc"; fi

# Generated for envman. Do not edit.
[ -s "$HOME/.config/envman/load.sh" ] && source "$HOME/.config/envman/load.sh"
