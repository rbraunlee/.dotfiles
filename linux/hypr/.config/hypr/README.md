# Hyprland screenshot shortcut

Super+Ctrl+Shift+S dispatches `flameshot gui` for interactive selection and
annotation. This binding does not start the tray application, save or upload a
capture, or fall back to Grim/Slurp/Swappy. Flameshot owns cancellation (Escape).
The existing Grim/Swappy configuration outside this shortcut is unchanged.

On the owner's native Wayland session, Flameshot needs the `flameshot`
executable and working `xdg-desktop-portal` with the Hyprland backend
(`xdg-desktop-portal-hyprland`). An installed executable alone does **not**
prove portal access or that a capture will work. See the
[Flameshot Wayland guide](https://flameshot.org/docs/guide/wayland-help/).
This package does not install dependencies, change portal permissions or
services, or set global Qt environment overrides.

Owner QA, only when ready to test on the live session: check availability with
`command -v flameshot` (without launching it); confirm the portal prerequisites
are working in your session; press Super+Ctrl+Shift+S and verify the selection
and annotation UI against harmless, non-sensitive on-screen content. Press
Escape and check that cancelling produces no capture/save. Check ordinary
multi-monitor usability and try the shortcut with Flameshot unavailable or
failing to launch to confirm no fallback capture occurs. These live checks,
especially portal access, cancellation and multi-monitor behavior, cannot be
established by the isolated Lua regression suite; do not assume success merely
because the shortcut dispatch is correct.

## Five-minute idle-lock request (startup/idle portion)

Hyprland's `hyprland.start` event is the sole repository startup owner for
`~/.config/hypr/start-hypridle.sh`; do not also enable a Hypridle user service.
The helper requires `hypridle`, `hyprlock` and `pgrep` on the session PATH. It
checks for an existing Hypridle process before launching one and reports missing
tools, process-check errors and daemon exits on stderr. A process check is **not**
proof of an active lock, a healthy daemon, or session-lock readiness; even a
successful start is not a verified protection state. A separate external startup
owner could exist outside this repository; the owner must reconcile it first.

The active 300-second listener requests `loginctl lock-session`; Hypridle's native
lock event uses the existing guarded `hyprlock` command. This needs a working
session/logind D-Bus lock signal and a compositor/locker supporting the Wayland
session-lock protocol, not just installed executables. Ordinary application idle
inhibitors remain honored. There is no screen-off, dimming, automatic suspend or
automatic unlock timer. The before-sleep lock request remains disabled in this
startup/idle portion; acknowledgement-aware pre-sleep configuration and its
release-support evidence belong to the following contribution. Do not infer
pre-sleep protection from this config. Before enabling pre-sleep locking,
verify the installed Hypridle release supports acknowledgement-aware
`inhibit_sleep = 3` using that exact release's help/docs/source; no minimum
release is asserted here.

Owner QA only after separately provisioning compatible tools and a recovery plan:
confirm a single daemon in the intended session, five uninhibited idle minutes
trigger a real lock that can be unlocked, normal inhibitors defer idle, and an
existing locker is not relaunched. These checks can lock out the session; tests
here use fake providers and cannot prove compositor lock readiness, logind
delivery or native daemon parsing. No tool installation, session activation or
live lock/suspend is performed by the package tests.
