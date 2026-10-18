# Local English dictation (Hyprland + Voxtype)

Stow package `linux/voxtype` contains `~/.config/voxtype/config.toml` and
`~/.config/systemd/user/voxtype.service`. The separate `linux/hypr` package
binds Super+Ctrl+D to `voxtype record toggle`; it does **not** start a daemon.
The systemd user unit starts `/usr/bin/voxtype -q daemon` at
`graphical-session.target`, stops with that target, and restarts on failure.
It has no `ydotool` dependency. Voxtype's internal evdev hotkey is disabled;
the shortcut needs no `input` group membership.

## Installed host and behavior (2026-10-18)

- Installed `voxtype-cuda 1.1.0-1` reports `voxtype 1.1.0+g67a503e`;
  `wtype 0.4-2` and `pipewire-alsa 1:1.6.9-1` are installed. The existing
  large-v3-turbo model is local; prior owner logs report CUDA on RTX 4090.
  `voxtype setup gpu --status` alone reported an unknown active backend.
  No model binaries, runtime state or host-specific audio source IDs are tracked.
- The installed-release settings use `whisper.mode = "local"`, English and
  large-v3-turbo. Type output uses **wtype only**; no clipboard fallback,
  remote endpoint, smart submit or automatic Enter is configured. Transcribed
  newlines request Shift+Enter. Recording start/stop notifications are enabled.
  `state_file = "auto"` supports the external toggle.
- The transcript goes to the field **focused at output time**, not a named
  OpenCode session. Release shortcut modifiers, keep focus in the draft, check
  the text and submit manually. Another focused field can receive output.
- The owner reported synthetic live dictation working (“Works perfectly”)
  after a toggle/feedback/draft/multiline/no-submit/changed-focus checklist.
  This is owner-reported success, not independent item-by-item observation.
  Since then the owner enabled a permanent Voxtype user service: read-only
  checks found it enabled/running with one daemon and no `Wants`, while the
  temporary QA unit is inactive. Its currently active HOME unit is a **regular
  file**, not a link to this package. No agent restarted it or repeated a
  microphone, typing or clipboard test after that switch. Post-switch draft
  behavior, authorized restart and **subsequent-login** startup remain owner QA.

The existing HOME Voxtype config symlink was migrated from the preserved
ticket-01 checkout to the human-merged, byte-identical
`~/.dotfiles/linux/voxtype/.config/voxtype/config.toml`. Its original link is
preserved under `~/.local/state/voxtype-dotfiles-backups/` in a private
timestamped `*-main-link-*` directory; preserve the old ticket worktree as
historical evidence. HOME Hyprland is an independent copy with the owner's
Super+Q close-key change; this package does not overwrite it. The new tracked
unit is for **future human adoption after merge**, not the active HOME unit.

## Setup and safe adoption after human merge

Install prerequisites on an appropriate Arch host (`voxtype-cuda`, `wtype`,
`pipewire-alsa`, an existing local model, and working PipeWire/Wayland); do not
reinstall or download the model on this already configured host. Check
`voxtype --version`, `command -v wtype`, `voxtype setup check`, and inspect
`systemctl --user status voxtype.service` and the two HOME paths before any
change. Do not assume this unit works with a different installed release.
Neither fixture tests nor a configured unit prove live audio/GPU/typing.

On the owner-approved adoption window, **after merging this change into
`~/.dotfiles`**, inspect and compare both package targets with their HOME
counterparts; note the current unit's enabled/running state and exact link
targets and hashes. Save the existing regular HOME unit (with its mode) in a
new owner-private (0700) timestamped backup under
`~/.local/state/voxtype-dotfiles-backups/`; preserve the HOME config link
itself too. Check for intervening edits immediately before each move. From
`~/.dotfiles`, dry-run `stow -n -d linux -t "$HOME" voxtype` first: an existing
regular service file is an expected **conflict**, not an invitation to `--adopt`
or force overwrite. Only once backed up, move **that one service file** out of
the way and rerun the dry run, then `stow -d linux -t "$HOME" voxtype`. Check
both HOME symlinks resolve into the merged `~/.dotfiles/linux/voxtype` package;
if the config link differs, back it up and resolve its content/target before
continuing. No broad Stow, Hyprland relink, input-group change or new daemon.

The running owner unit is left alone by merely adding the tracked file. At a
separately owner-chosen restart/verification time, check for recording activity
first; then use `systemctl --user daemon-reload`, confirm enabled state and unit
resolution, and explicitly authorize any `systemctl --user restart
voxtype.service`. Confirm only one daemon remains and use harmless synthetic
draft/no-submit and alternate-focus checks; the owner checks startup again at
the **next login**. Do not claim persistence from `WantedBy` or `enabled`
alone. Do not start the inactive temporary QA unit as a second daemon.

## Disable / rollback (only for changes actually performed)

Preserve any newer edits before rollback and record the current enabled/active
state. If intentionally disabling dictation, end any recording under owner
supervision and stop/disable only `voxtype.service`; leave other services and
model/runtime data alone. If undoing a service-link adoption, after checking
the HOME unit link still points to this package, unlink only that link and
restore its backed-up regular file with its original mode/content; reload the
user manager and restore its **recorded** enabled/active state at an agreed
time, without an unrequested restart. If undoing the config-link migration,
verify the link still targets `~/.dotfiles` and no user edits were made, then
restore the saved original symlink **at the HOME path** (its relative target is
not valid when read from the backup directory); keep the ticket worktree until
that decision is final. Otherwise preserve the current merged config link.
To undo the shortcut, restore the separately backed-up HOME Hyprland copy only
after checking for newer edits, then perform a targeted reload with owner
agreement. Never force-unstow, delete backups, or overwrite unrelated changes.
