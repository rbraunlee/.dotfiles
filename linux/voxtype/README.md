# Local English dictation — staged, not activated

Stow `linux/voxtype` supplies `~/.config/voxtype/config.toml`. Hyprland's
Super+Ctrl+D calls `voxtype record toggle`; the daemon (not Hyprland) owns
recording. The internal evdev hotkey is disabled, so no `input` group change is
required for the toggle. `state_file = "auto"` supports external toggling.
Whisper uses the installed large-v3-turbo model, English and **local** mode;
the host's installed `voxtype-cuda` build is used unchanged. No remote endpoint,
model binary, audio source ID or runtime state belongs in this package.

Output is type mode with wtype only; there is no clipboard fallback, automatic
Enter or spoken smart-submit. Multi-line transcripts request Shift+Enter rather
than Enter. Recording start/stop notifications signal recording/transcribing;
this is configured behavior, not yet verified live. The transcript is delivered
to the **field focused at output time**, not to an OpenCode session. Release the
shortcut modifiers, keep focus in the draft, and inspect before manually sending.
An alternate focused field may receive the text if focus changes.

## Inspected host (2026-10-18; read-only)

`voxtype --version` reports `1.1.0+g67a503e` (`voxtype-cuda 1.1.0-1`), not
the previously staged v1.1.1 Vulkan release. `voxtype setup check` finds
large-v3-turbo installed (1549 MB), wl-copy available and no typing drivers;
`pipewire-alsa 1:1.6.9-1` is installed. `wtype`, `ydotool` and `eitype` are
absent. Prior owner logs (not reproduced here) report the CUDA model loaded on
RTX 4090 and successful transcription **to clipboard**, not draft insertion.
`voxtype setup gpu --status` reports unknown active backend in its simple-build
inventory; it does not override the owner's CUDA runtime logs. The current
regular-file HOME config has hotkey off, English large-v3-turbo, default local
mode and type output, but clipboard fallback on, no typing driver installed,
no Shift+Enter or start/stop notification enabled. The new config explicitly
sets `whisper.mode = "local"` (not the old `whisper.backend` key), restricts
`driver_order` to wtype and disables both clipboard fallback and submit paths.
`voxtype -c linux/voxtype/.config/voxtype/config.toml config get --json`
confirmed the installed binary resolves the local, hotkey, output, fallback,
auto-submit, Shift+Enter and smart-submit values. No recording was initiated.
`systemctl --user` reports voxtype disabled/inactive; the vendor unit is
`/usr/lib/systemd/user/voxtype.service` (ticket 02 owns persistence). HOME's
Hyprland Lua is a symlink into the **dirty protected main checkout**; this
ticket does not edit or reload it. Compared with prior commit `0917b449`,
the shortcut and Stow layout are reusable; its v1.1.1/Vulkan provisioning
claims and `whisper.backend` setting are not.

## Proposed activation, pending separate owner agreement

**Do not run this against HOME until the owner approves this exact reversible
method, a safe backup location and supervised QA.** First install only the
demonstrably missing `wtype` after approval (do not reinstall Voxtype, download
a model, alter input groups or modify other services). Recheck `command -v
wtype` and run `voxtype setup check`. Select a timestamped, owner-private
directory outside Stow and Git, chmod 700, and record original link targets,
permissions, service enabled/active states and checksums. Copy the existing
regular HOME Voxtype config there with restrictive permissions. Back up the
HOME Hyprland Lua *symlink itself* and a copy of its current target content,
including the owner's uncommitted close-key change. Confirm the two target
paths and absence of intervening edits immediately before activation.

Move **only** the existing Voxtype config out of the way into that backup,
dry-run `stow -n -d <feature-worktree>/linux -t "$HOME" voxtype`, then stow
only `voxtype` (never `--adopt`). For Hyprland, replace only the HOME
`hyprland.lua` link with an owner-approved independent copy of its backed-up
live target plus this one toggle binding; do not modify the normal checkout,
switch branches, restow Hyprland or replace the owner's close-key change. After
comparing that copy against the backed-up source, reload only Hyprland using its
targeted reload command. This is a **proposal**, not an instruction to mutate
HOME without agreement; the exact overlay and backup location need owner signoff.
If the copied config drifts from the repository version, resolve explicitly
rather than replacing either file. Ticket 02 owns authorized Voxtype service
activation/restart and persistence; record prior state for restoration.

To disable/rollback after an approved activation, cancel any recording under
owner supervision, stop/disable only the Voxtype user service **if this feature
started/enabled it**, remove only the dedicated toggle via restoration of the
backed-up HOME Hyprland symlink (checking for newer edits first), and reload
only Hyprland. Unstow only Voxtype after verifying the link still belongs to
this package; restore the backed-up regular config with its original mode and
contents, then restore the original service state. Preserve all intervening
user edits, never force-unstow or discard model/runtime data.

Before claiming delivery, arrange owner-supervised synthetic microphone QA:
confirm toggle start/stop and visible feedback, local English output into an
empty OpenCode draft, multi-line Shift+Enter without submission, and a separate
harmless field receiving output after changing focus. An absent typing driver
should fail rather than silently write the clipboard. Neither the config tests
nor owner-reported clipboard success prove microphone, GPU, notifications,
Wayland typing, focus routing, or no-submit behavior of the installed binary.
