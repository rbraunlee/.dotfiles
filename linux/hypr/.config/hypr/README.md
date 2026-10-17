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

## Five-minute idle lock and pre-sleep lock request

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
automatic unlock timer. Before externally requested sleep, Hypridle requests
`loginctl lock-session`, the same native lock event and guarded `lock_cmd` used
for idle locking. The existing `hyprctl dispatch dpms on` runs after resume.
Explicit `inhibit_sleep = 3` selects Wayland session-lock acknowledgement, not
command launch, process existence or a fixed delay, as the readiness signal.

Release evidence: the upstream **Hypridle v0.1.8** tag (commit
`e5c01af0842bd66617f7004568df9406111d6e80`) registers
[`general:inhibit_sleep` in src/config/ConfigManager.cpp](https://github.com/hyprwm/hypridle/blob/v0.1.8/src/config/ConfigManager.cpp#L70-L75).
Its [src/core/Hypridle.cpp lines 103–138](https://github.com/hyprwm/hypridle/blob/v0.1.8/src/core/Hypridle.cpp#L103-L138)
map mode 3 to `SLEEP_INHIBIT_LOCK_NOTIFY` **only when** the compositor supplies
`hyprland-lock-notify-v1`; [onLocked() lines 398–415](https://github.com/hyprwm/hypridle/blob/v0.1.8/src/core/Hypridle.cpp#L398-L415)
release the sleep inhibitor on the locked notification, while
[PrepareForSleep lines 490–513](https://github.com/hyprwm/hypridle/blob/v0.1.8/src/core/Hypridle.cpp#L490-L513)
run the before/after commands. This establishes support in that exact release,
**not** a minimum supported version or proof about whichever binary is installed.
Verify the installed release's matching help/source and native config parsing before
relying on it. Without the lock-notify protocol, a working Hyprlock/session-lock
handshake and logind's session and sleep delay inhibitor interfaces, mode 3 does
not establish readiness; upstream warns it will not work without the protocol.
Missing tools, failed lock requests, an existing process or a daemon launch are
not evidence that a session is locked. The logind delay inhibitor has an OS-configured
timeout and forced sleep can bypass it: this is **not** an unlimited or fail-closed
veto of suspend. Recoverability and actual lock-before-sleep behavior require
native validation, not the fake-event regressions here.

Owner QA only after separately provisioning compatible tools and a recovery plan:
confirm a single daemon in the intended session, five uninhibited idle minutes
trigger a real lock that can be unlocked, normal inhibitors defer idle, and an
existing locker is not relaunched. Also validate installed-version config parsing,
logind session delivery, a real pre-sleep lock acknowledgement and display
restoration after resume; plan a recovery path before any lock/suspend test and
account for the OS delay timeout and forced sleep. These checks can lock out the
session; tests here use fake providers and cannot prove compositor lock readiness,
native daemon parsing or logind delay behavior. No tool installation, session
activation or live lock/suspend is performed by the package tests.
