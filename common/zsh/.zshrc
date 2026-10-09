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

# Defaults apply only when the caller has not made a usable selection. Zsh
# records multiline commands as one history entry without Bash's cmdhist.
: ${EDITOR:=nvim}
: ${VISUAL:=$EDITOR}
: ${HISTFILE:=$HOME/.zsh_history}
# Zsh initializes HISTSIZE to 30 even under -f; replace that small built-in
# default while leaving other caller-selected sizes alone.
if [[ $HISTSIZE -eq 30 ]]; then HISTSIZE=10000; fi
# SAVEHIST is also an integer-special parameter, initialized to zero.
if [[ $SAVEHIST -eq 0 ]]; then SAVEHIST=10000; fi
export EDITOR VISUAL
setopt APPEND_HISTORY HIST_IGNORE_ALL_DUPS HIST_IGNORE_SPACE HIST_SAVE_NO_DUPS

# Honor an installed caller-selected toolkit. Only choose the conventional
# system location when no CUDA_HOME was selected; never add a missing toolkit.
if [[ -z $CUDA_HOME && -d /opt/cuda/bin ]]; then
    export CUDA_HOME=/opt/cuda
fi
if [[ -n $CUDA_HOME && -d "$CUDA_HOME/bin" && ${path[(Ie)$CUDA_HOME/bin]} -eq 0 ]]; then
    path=( "$CUDA_HOME/bin" $path )
fi

# Keep the caller's existing PATH order, including on repeated `reload`.
() {
    local user_bin
    for user_bin in "$HOME/.bin" "$HOME/.local/bin"; do
        if [[ -d "$user_bin" && ${path[(Ie)$user_bin]} -eq 0 ]]; then
            path=( "$user_bin" $path )
        fi
    done
}

alias v="nvim"
alias vim="nvim"
alias reload="source ~/.zshrc"

# Everyday portable listings and disk space.
alias la='ls -a'
alias ll='ls -alFh'
alias df='df -h'

# Extract one existing archive in the current directory. This is not a sandbox:
# only open archives from trusted sources (archive members may escape the cwd).
ex() {
    if (( $# != 1 )); then
        print -u2 -- 'ex: expected exactly one archive filename'
        return 2
    fi
    if [[ ! -f $1 ]]; then
        print -u2 -- "ex: expected an existing archive file: $1"
        return 2
    fi

    # Prefix option-looking relative filenames rather than assuming every
    # extractor supports -- (notably ar, unrar, 7z and older unzip versions).
    local archive=$1 tool exit_code
    [[ $archive == -* ]] && archive=./$archive
    local -a flags
    case $archive in
        (*.tar.bz2|*.tbz2) tool=tar; flags=(xjf) ;;
        (*.tar.gz|*.tgz)   tool=tar; flags=(xzf) ;;
        (*.tar|*.tar.xz|*.tar.zst) tool=tar; flags=(xf) ;;
        (*.bz2) tool=bunzip2 ;;
        (*.rar) tool=unrar; flags=(x) ;;
        (*.gz)  tool=gunzip ;;
        (*.zip) tool=unzip ;;
        (*.Z)   tool=uncompress ;;
        (*.7z)  tool=7z; flags=(x) ;;
        (*.deb) tool=ar; flags=(x) ;;
        (*) print -u2 -- "ex: unsupported archive type: $1"; return 2 ;;
    esac
    if ! command -v "$tool" >/dev/null 2>&1; then
        print -u2 -- "ex: required extractor not found: $tool"
        return 127
    fi
    command "$tool" "${flags[@]}" "$archive"
    exit_code=$?
    if (( exit_code )); then
        print -u2 -- "ex: $tool failed for $1 (status $exit_code)"
    fi
    return $exit_code
}

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

    alias free='free -mt'
    alias psa='ps auxf'
    alias jctl='journalctl -p 3 -xb'
    alias sysfailed='systemctl list-units --failed'

    psgrep() {
        setopt localoptions pipefail
        if (( $# != 1 )) || [[ -z $1 ]]; then
            print -u2 -- 'psgrep: expected one process name'
            return 2
        fi
        if ! command -v ps >/dev/null || ! command -v grep >/dev/null; then
            print -u2 -- 'psgrep: requires ps and grep'
            return 127
        fi
        command ps aux | command grep -i -F -e VSZ -e "$1"
    }

    audio() {
        setopt localoptions pipefail
        if ! command -v pactl >/dev/null || ! command -v grep >/dev/null; then
            print -u2 -- 'audio: requires pactl and grep'
            return 127
        fi
        command pactl info | command grep -F 'Server Name'
    }
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
