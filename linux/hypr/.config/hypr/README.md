# Hyprland screenshot shortcut

Super+Ctrl+D dispatches `voxtype record toggle` for local dictation. See
`linux/voxtype/README.md` for unactivated host setup, focus risk and proposed
scoped backup/rollback. It neither launches a daemon at login nor submits text.

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
