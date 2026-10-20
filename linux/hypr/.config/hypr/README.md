# Hyprland startup and shortcuts

At `hyprland.start` (not on config reload), the existing autostarts run and
Hyprland imports `WAYLAND_DISPLAY`, `DISPLAY`, `XDG_CURRENT_DESKTOP`,
`XDG_SESSION_TYPE`, and `HYPRLAND_INSTANCE_SIGNATURE` into the systemd user
manager, then calls `systemctl --user start voxtype.service` only if import
succeeds. This starts the existing managed unit even when
`graphical-session.target` is inactive under `start-hyprland`; it does not
start that target, restart an active service, or spawn an unmanaged daemon.
Super+Ctrl+D still dispatches only `voxtype record toggle`, never submits text.
Super+Q closes the focused window. See `linux/voxtype/README.md` for safe
post-merge adoption of the independent HOME Hyprland copy and next-login QA.

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
