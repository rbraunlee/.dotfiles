#!/bin/sh
# Launched by Hyprland's hyprland.start event; this only checks availability.
if ! command -v hypridle >/dev/null 2>&1; then
    printf '%s\n' 'Hypridle startup: hypridle not found on PATH; idle locking is unavailable.' >&2
    exit 1
fi
if ! command -v hyprlock >/dev/null 2>&1; then
    printf '%s\n' 'Hypridle startup: hyprlock not found on PATH; idle locking is unavailable.' >&2
    exit 1
fi
if ! command -v pgrep >/dev/null 2>&1; then
    printf '%s\n' 'Hypridle startup: pgrep not found on PATH; cannot safely check for an existing daemon.' >&2
    exit 1
fi
if pgrep -x hypridle >/dev/null 2>&1; then
    exit 0 # Existing process is not evidence that the session is locked or protected.
else
    status=$?
    if [ "$status" -ne 1 ]; then
        printf 'Hypridle startup: pgrep failed (status %s); cannot safely check for an existing daemon.\n' "$status" >&2
        exit 1
    fi
fi
hypridle
status=$?
printf 'Hypridle startup: hypridle exited with status %s; idle locking is unavailable.\n' "$status" >&2
if [ "$status" -eq 0 ]; then
    exit 1 # Even a clean exit means the daemon no longer provides idle locking.
fi
exit "$status"
