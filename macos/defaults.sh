#!/usr/bin/env bash
# Apply macOS `defaults` that make the desktop behave closer to the Hyprland setup.
#
# Idempotent: re-running rewrites the same values. Nothing is installed.
# Preview without changing anything:   DRY_RUN=1 macos/defaults.sh
# Also auto-hide the menu bar:         HIDE_MENU_BAR=1 macos/defaults.sh
#
# Kept bash 3.2 compatible because that is what /bin/bash is on macOS.
set -euo pipefail

if [ "$(uname -s)" != "Darwin" ]; then
  echo "defaults.sh only runs on macOS (uname: $(uname -s))" >&2
  exit 1
fi

DRY_RUN="${DRY_RUN:-0}"
HIDE_MENU_BAR="${HIDE_MENU_BAR:-0}"

# Print each change; only execute it when not a dry run.
set_default() {
  echo "defaults write $*"
  if [ "$DRY_RUN" != "1" ]; then
    defaults write "$@"
  fi
}

echo "== Window animations =="
# Instant window open/close/resize, closer to Hyprland with animations off.
set_default NSGlobalDomain NSAutomaticWindowAnimationsEnabled -bool false
set_default NSGlobalDomain NSWindowResizeTime -float 0.001

echo "== Dock =="
# Hide the Dock and remove the reveal delay and slide animation.
set_default com.apple.dock autohide -bool true
set_default com.apple.dock autohide-delay -float 0
set_default com.apple.dock autohide-time-modifier -float 0
set_default com.apple.dock show-recents -bool false

echo "== Spaces (AeroSpace needs these) =="
# AeroSpace manages its own workspaces, so stop macOS reordering Spaces by use.
set_default com.apple.dock mru-spaces -bool false
# "Displays have separate Spaces" ON == spans-displays false. Needs a logout.
set_default com.apple.spaces spans-displays -bool false

echo "== Keyboard =="
# Key repeat instead of the accent popup; fast repeat like an X/Wayland session.
set_default NSGlobalDomain ApplePressAndHoldEnabled -bool false
set_default NSGlobalDomain KeyRepeat -int 2
set_default NSGlobalDomain InitialKeyRepeat -int 15
# Turn off text "helpfulness" that mangles code and terminal input.
set_default NSGlobalDomain NSAutomaticSpellingCorrectionEnabled -bool false
set_default NSGlobalDomain NSAutomaticCapitalizationEnabled -bool false
set_default NSGlobalDomain NSAutomaticQuoteSubstitutionEnabled -bool false
set_default NSGlobalDomain NSAutomaticDashSubstitutionEnabled -bool false
set_default NSGlobalDomain NSAutomaticPeriodSubstitutionEnabled -bool false

echo "== Finder =="
set_default com.apple.finder AppleShowAllFiles -bool true
set_default NSGlobalDomain AppleShowAllExtensions -bool true
set_default com.apple.finder ShowPathbar -bool true
set_default com.apple.finder _FXSortFoldersFirst -bool true
set_default com.apple.finder FXEnableExtensionChangeWarning -bool false
# Default to list view (Nlsv); icnv=icon, clmv=column, glyv=gallery.
set_default com.apple.finder FXPreferredViewStyle -string Nlsv

if [ "$HIDE_MENU_BAR" = "1" ]; then
  echo "== Menu bar =="
  set_default NSGlobalDomain _HIHideMenuBarAutomatically -bool true
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "Dry run: nothing written."
  exit 0
fi

# Restart the affected processes so changes show up without a logout.
for app in Dock Finder SystemUIServer; do
  killall "$app" >/dev/null 2>&1 || true
done

cat <<'EOF'

Done. Some settings need a logout/login: separate Spaces, key repeat, text substitution.

Not set here (macOS blocks or cannot persist these via `defaults`):
  - Reduce motion: System Settings > Accessibility > Display
  - Caps Lock -> Escape/Ctrl: System Settings > Keyboard > Keyboard Shortcuts > Modifier Keys
    (or Karabiner-Elements; `hidutil` does not survive a reboot)
EOF
