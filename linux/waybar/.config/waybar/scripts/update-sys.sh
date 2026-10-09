#!/usr/bin/env bash

# Original script by @speltriao on GitHub
# https://github.com/speltriao/Pacman-Update-for-GNOME-Shell

# If the operating system is not Arch Linux, exit the script successfully
if [ ! -f "${WAYBAR_ARCH_RELEASE_FILE:-/etc/arch-release}" ]; then
    exit 0
fi

if [ "$1" = "update" ]; then
    if ! command -v yay >/dev/null 2>&1; then
        printf 'Cannot launch updates: yay is unavailable\n' >&2
        exit 1
    fi
    if ! command -v sh >/dev/null 2>&1; then
        printf 'Cannot launch updates: sh is unavailable\n' >&2
        exit 1
    fi
    if ! command -v ghostty >/dev/null 2>&1; then
        printf 'Cannot launch updates: Ghostty is unavailable\n' >&2
        exit 1
    fi
    ghostty --title=update-sys -e sh -c 'yay -Syu'
    status=$?
    if ((status != 0)); then
        printf 'Ghostty launch failed (status %s)\n' "$status" >&2
    fi
    exit "$status"
fi

# Count only provider listings, not diagnostic text emitted on stdout.
count_list() {
    local listing=$1 line
    local update_line='^[^[:space:]]+[[:space:]]+[^[:space:]]+[[:space:]]+->[[:space:]]+[^[:space:]]+$'
    COUNT=0
    [[ -z $listing ]] && return 0
    while IFS= read -r line; do
        [[ $line =~ $update_line ]] || return 1
        ((COUNT+=1))
    done <<< "$listing"
}

unavailable() {
    echo "Updates unavailable"
    exit 0  # Waybar must render this text, even when a query failed.
}

case $1 in
    ''|aur|official) ;;
    *) exit 0 ;;
esac

if [[ $1 != official ]]; then
    command -v yay >/dev/null 2>&1 || unavailable
    listing=$(yay -Qua)
    status=$?
    ((status == 0)) && count_list "$listing" || unavailable
    AUR=$COUNT
fi

if [[ $1 != aur ]]; then
    command -v checkupdates >/dev/null 2>&1 || unavailable
    listing=$(checkupdates)
    status=$?
    if ((status == 2)); then
        [[ -z $listing ]] || unavailable
        OFFICIAL=0
    else
        ((status == 0)) && count_list "$listing" || unavailable
        OFFICIAL=$COUNT
    fi
fi

case $1 in
    aur) echo " $AUR" ;;
    official) echo " $OFFICIAL" ;;
    '')
        COUNT=$((OFFICIAL+AUR))
        if ((COUNT == 0)); then
            echo ""
        else
            echo " $COUNT"
        fi ;;
esac
