# tmux package

tmux-continuum restores sessions automatically and saves every five minutes;
tmux-resurrect captures pane contents. Saved terminal output may include sensitive
text and persist locally. Keep snapshot storage private and use an appropriate
retention policy; this package does not inspect or delete existing snapshots.
Additional program restoration uses tmux-resurrect's conservative defaults, not
restore-all.

From the repository root, run
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/common/tmux -v`.
The suite starts disposable tmux servers on private sockets and removes TPM's
bootstrap only from its fixture. It inspects native options and bindings, not
real plugins, saved sessions, clipboard integration or visible true color.
Check those behaviors separately in an owner-approved isolated live session
using synthetic content only.
