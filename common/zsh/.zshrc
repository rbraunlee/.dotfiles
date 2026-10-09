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

# Explicit media downloads only. ffmpeg supplies yt-dlp's extraction/merge
# conversions; neither optional provider is consulted at shell startup.
_media_download() {
    local format=$1
    shift
    (( $# )) || { print -u2 -- 'media: expected at least one URL'; return 2; }
    local provider
    for provider in yt-dlp ffmpeg; do
        if ! whence -p -- "$provider" >/dev/null 2>&1; then
            print -u2 -- "media: required command not found: $provider"
            return 127
        fi
    done
    if [[ $format == video ]]; then
        command yt-dlp -f 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio' --merge-output-format mp4 -- "$@"
    else
        command yt-dlp -x --audio-format "$format" -- "$@"
    fi
}
yta-aac() { _media_download aac "$@"; }
yta-best() { _media_download best "$@"; }
yta-flac() { _media_download flac "$@"; }
yta-mp3() { _media_download mp3 "$@"; }
ytv-best() { _media_download video "$@"; }

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

    # Pass an absolute local filename to every provider: GNU tar treats a
    # relative host:name archive as a remote host, and some extractors do not
    # support -- for option-looking names. Match the supplied extension before
    # canonicalizing so a symlink's advertised archive type is respected.
    local archive=${1:A} tool exit_code
    local -a flags
    case $1 in
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

    # Resolve providers at invocation, not startup. `command pacman` bypasses
    # the interactive pacman=sudo alias for every read-only query.
    _arch_require() {
        local provider
        for provider in "$@"; do
            if ! whence -p -- "$provider" >/dev/null 2>&1; then
                print -u2 -- "Arch helper: required command not found: $provider"
                return 127
            fi
        done
    }
    _arch_package_args() {
        local package
        (( $# )) || { print -u2 -- 'Arch helper: expected a package'; return 2; }
        for package in "$@"; do
            if [[ -z $package || $package == -* ]]; then
                print -u2 -- 'Arch helper: expected package names, not options'
                return 2
            fi
        done
    }

    # Generate unprivileged output first; stage as root in the mirrorlist's
    # directory so the final rename cannot cross filesystem boundaries.
    _mirror_select() {
        local generator=$1
        shift
        (( $# )) || { print -u2 -- 'mirror: missing selector'; return 2; }
        _arch_require "$generator" sudo mktemp rm || return $?
        local target=/etc/pacman.d/mirrorlist
        local candidate stage
        candidate=$(command mktemp "${TMPDIR:-/tmp}/zsh-mirror-candidate.XXXXXXXX") || {
            print -u2 -- 'mirror: unable to create candidate'; return 1
        }
        if ! command "$generator" "$@" > "$candidate" || [[ ! -s $candidate || ! -r $candidate ]]; then
            print -u2 -- 'mirror: generator failed or candidate is empty/unreadable'
            command rm -f -- "$candidate" || print -u2 -- 'mirror: candidate cleanup failed'
            return 1
        fi
        if ! command sudo cp -p -- "$target" "${target}.backup"; then
            print -u2 -- 'mirror: backup failed'
            command rm -f -- "$candidate" || print -u2 -- 'mirror: candidate cleanup failed'
            return 1
        fi
        stage=$(command sudo mktemp "${target}.XXXXXXXX") || {
            print -u2 -- 'mirror: privileged staging failed'
            command rm -f -- "$candidate" || print -u2 -- 'mirror: candidate cleanup failed'
            return 1
        }
        # Reject unexpected sudo output before using it as a privileged path.
        local stage_pattern='^/etc/pacman[.]d/mirrorlist[.][[:alnum:]]{8}$'
        if [[ ! $stage =~ $stage_pattern ]]; then
            print -u2 -- 'mirror: unexpected staging path'
            command rm -f -- "$candidate" || print -u2 -- 'mirror: candidate cleanup failed'
            return 1
        fi
        if ! command sudo install -m 644 -- "$candidate" "$stage"; then
            print -u2 -- 'mirror: privileged staging write failed'
            command sudo rm -f -- "$stage" || print -u2 -- 'mirror: staging cleanup failed'
            command rm -f -- "$candidate" || print -u2 -- 'mirror: candidate cleanup failed'
            return 1
        fi
        if ! command sudo mv -f -T -- "$stage" "$target"; then
            print -u2 -- 'mirror: atomic publication failed'
            command sudo rm -f -- "$stage" || print -u2 -- 'mirror: staging cleanup failed'
            command rm -f -- "$candidate" || print -u2 -- 'mirror: candidate cleanup failed'
            return 1
        fi
        if ! command rm -f -- "$candidate"; then
            print -u2 -- 'mirror: candidate cleanup failed'
            return 1
        fi
    }
    mirror() { (( $# == 0 )) || { print -u2 -- 'mirror: takes no arguments'; return 2; }; _mirror_select reflector -f 30 -l 30 --number 10 --verbose; }
    mirrord() { (( $# == 0 )) || { print -u2 -- 'mirrord: takes no arguments'; return 2; }; _mirror_select reflector --latest 30 --number 10 --sort delay; }
    mirrors() { (( $# == 0 )) || { print -u2 -- 'mirrors: takes no arguments'; return 2; }; _mirror_select reflector --latest 30 --number 10 --sort score; }
    mirrora() { (( $# == 0 )) || { print -u2 -- 'mirrora: takes no arguments'; return 2; }; _mirror_select reflector --latest 30 --number 10 --sort age; }
    mirrorx() { (( $# == 0 )) || { print -u2 -- 'mirrorx: takes no arguments'; return 2; }; _mirror_select reflector --age 6 --latest 20 --fastest 20 --threads 5 --sort rate --protocol https; }
    mirrorxx() { (( $# == 0 )) || { print -u2 -- 'mirrorxx: takes no arguments'; return 2; }; _mirror_select reflector --age 6 --latest 20 --fastest 20 --threads 20 --sort rate --protocol https; }
    ram() { (( $# == 0 )) || { print -u2 -- 'ram: takes no arguments'; return 2; }; _mirror_select rate-mirrors --allow-root --disable-comments arch; }
    rams() { (( $# == 0 )) || { print -u2 -- 'rams: takes no arguments'; return 2; }; _mirror_select rate-mirrors --allow-root --disable-comments --protocol https arch; }

    sps() {
        _arch_package_args "$@" || return $?
        _arch_require sudo pacman || return $?
        command sudo pacman -S "$@"
    }
    spr() {
        _arch_package_args "$@" || return $?
        _arch_require sudo pacman || return $?
        command sudo pacman -R "$@"
    }
    sprs() {
        _arch_package_args "$@" || return $?
        _arch_require sudo pacman || return $?
        command sudo pacman -Rs "$@"
    }
    spqo() {
        (( $# )) || { print -u2 -- 'spqo: expected a path'; return 2; }
        _arch_require pacman || return $?
        command pacman -Qo -- "$@"
    }
    spsii() {
        (( $# )) || { print -u2 -- 'spsii: expected a package'; return 2; }
        _arch_require pacman || return $?
        command pacman -Sii -- "$@"
    }
    depends() {
        (( $# == 1 )) && [[ -n $1 ]] || { print -u2 -- 'depends: expected one package'; return 2; }
        _arch_require pacman || return $?
        local info
        info=$(command pacman -Sii -- "$1") || return $?
        local line
        for line in "${(@f)info}"; do
            if [[ $line == 'Required By '* ]]; then
                print -r -- "${line#*: }"
            fi
        done
    }
    list() {
        (( $# == 0 )) || { print -u2 -- 'list: takes no arguments'; return 2; }
        _arch_require pacman || return $?
        command pacman -Qqe
    }
    listt() {
        (( $# == 0 )) || { print -u2 -- 'listt: takes no arguments'; return 2; }
        _arch_require pacman || return $?
        command pacman -Qqet
    }
    listaur() {
        (( $# == 0 )) || { print -u2 -- 'listaur: takes no arguments'; return 2; }
        _arch_require pacman || return $?
        command pacman -Qqem
    }
    update() {
        (( $# == 0 )) || { print -u2 -- 'update: takes no arguments'; return 2; }
        _arch_require sudo pacman || return $?
        command sudo pacman -Syu
    }
    upall() {
        (( $# == 0 )) || { print -u2 -- 'upall: takes no arguments'; return 2; }
        _arch_require paru || return $?
        command paru -Syu
    }
    upd() { update "$@"; }
    upa() { upall "$@"; }
    cleanup() {
        (( $# == 0 )) || { print -u2 -- 'cleanup: takes no arguments'; return 2; }
        _arch_require pacman mktemp rm || return $?
        local diagnostic_file orphans query_status query_error
        diagnostic_file=$(command mktemp "${TMPDIR:-/tmp}/zsh-arch-cleanup.XXXXXXXX") || {
            print -u2 -- 'cleanup: unable to create diagnostic file'
            return 1
        }
        # Pacman convention: -Qtdq exits 1 with empty stdout/stderr when no
        # orphans match. A diagnostic (even with status 1 or 0) is an error.
        # Keep stderr separate: a warning resembling a package name must
        # never become a target of the subsequent privileged removal.
        orphans=$(command pacman -Qtdq 2>"$diagnostic_file")
        query_status=$?
        if [[ ! -f $diagnostic_file || ! -r $diagnostic_file ]]; then
            command rm -f -- "$diagnostic_file" >/dev/null 2>&1
            print -u2 -- 'cleanup: unable to read diagnostic file'
            return 1
        fi
        query_error=$(<"$diagnostic_file") || {
            command rm -f -- "$diagnostic_file" >/dev/null 2>&1
            print -u2 -- 'cleanup: unable to read diagnostic file'
            return 1
        }
        if ! command rm -f -- "$diagnostic_file"; then
            print -u2 -- 'cleanup: unable to remove diagnostic file'
            return 1
        fi
        if [[ -n $query_error ]] || { (( query_status != 0 )) && { (( query_status != 1 )) || [[ -n $orphans ]]; }; }; then
            print -u2 -- "cleanup: orphan query failed (status $query_status)"
            [[ -z $query_error ]] || print -u2 -r -- "$query_error"
            (( query_status )) && return $query_status
            return 1
        fi
        [[ -n $orphans ]] || { print -r -- 'cleanup: no orphans'; return 0; }
        local -a packages
        packages=( "${(@f)orphans}" )
        local package
        # Only provider-native package identifiers may be removed.
        for package in "${packages[@]}"; do
            if [[ ! $package =~ '^[a-zA-Z0-9@._+-]+$' ]]; then
                print -u2 -- "cleanup: unexpected orphan query output: $package"
                return 1
            fi
        done
        _arch_require sudo || return $?
        command sudo pacman -Rns -- "${packages[@]}"
    }
    rip() {
        (( $# == 0 )) || { print -u2 -- 'rip: takes no arguments'; return 2; }
        _arch_require expac sort tail nl || return $?
        setopt localoptions pipefail
        command expac '--timefmt=%Y-%m-%d %T' '%l\t%n %v' |
            command sort | command tail -200 | command nl
    }
    riplong() {
        (( $# == 0 )) || { print -u2 -- 'riplong: takes no arguments'; return 2; }
        _arch_require expac sort tail nl || return $?
        setopt localoptions pipefail
        command expac '--timefmt=%Y-%m-%d %T' '%l\t%n %v' |
            command sort | command tail -3000 | command nl
    }
    big() {
        (( $# == 0 )) || { print -u2 -- 'big: takes no arguments'; return 2; }
        _arch_require expac sort nl || return $?
        setopt localoptions pipefail
        command expac -H M '%m\t%n' | command sort -h | command nl
    }

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

    # wf-recorder selects the available codecs; no GPU/VAAPI device is assumed.
    wsimplescreen() {
        (( $# == 0 )) || { print -u2 -- 'wsimplescreen: takes no arguments'; return 2; }
        if ! whence -p -- wf-recorder >/dev/null 2>&1; then
            print -u2 -- 'wsimplescreen: required command not found: wf-recorder'
            return 127
        fi
        command wf-recorder -a
    }
    wsimplescreenrecorder() {
        (( $# <= 1 )) && [[ ${1-recording.mp4} == *.mp4 ]] || {
            print -u2 -- 'wsimplescreenrecorder: expected at most one .mp4 output filename'
            return 2
        }
        local output=${1-recording.mp4}
        if [[ -e $output || -L $output ]]; then
            print -u2 -- "wsimplescreenrecorder: output already exists: $output"
            return 1
        fi
        if ! whence -p -- wf-recorder >/dev/null 2>&1; then
            print -u2 -- 'wsimplescreenrecorder: required command not found: wf-recorder'
            return 127
        fi
        command wf-recorder -a -f "$output"
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
