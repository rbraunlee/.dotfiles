# tmux package

## Install

Requires tmux, Git and GNU Stow. From the repository root:

```sh
stow -n -v --no-folding -t ~ -d common tmux
stow --no-folding -t ~ -d common tmux
mkdir -p ~/.tmux/plugins
git clone https://github.com/tmux-plugins/tpm ~/.tmux/plugins/tpm
```

Clone TPM only if it is not already installed. Start tmux and press `Ctrl-b`
then uppercase `I` to install the declared plugins. For an existing session,
reload first with `tmux source-file ~/.config/tmux/tmux.conf`.

TPM manages all plugin downloads in `~/.tmux/plugins/`. The configuration sets
`TMUX_PLUGIN_MANAGER_PATH` explicitly because [TPM otherwise selects the XDG
configuration directory](https://github.com/tmux-plugins/tpm/blob/master/tpm)
when an XDG tmux config exists. Plugins are not Git submodules of this repository.
Stow manages only the configuration; it does not download or update plugins.

Older checkouts may retain `.config/tmux/plugins/` inside this package. Those
directories are ignored by both Git and Stow and are left untouched. If you used
that location, preserve it until the new TPM installation works; install plugins
through TPM at the new path. Existing links created by the old package should be
reviewed before restowing. Do not delete plugin data or session snapshots merely
to resolve a Stow conflict.

Restow or unlink the configuration with:

```sh
stow -R --no-folding -t ~ -d common tmux
stow -D --no-folding -t ~ -d common tmux
```

Unstowing leaves `~/.tmux/plugins` and saved session data intact.

## Persistence

tmux-continuum restores sessions automatically and saves every five minutes;
tmux-resurrect captures pane contents. Saved terminal output may include sensitive
text and persist locally. Keep snapshot storage private and use an appropriate
retention policy; this package does not inspect or delete existing snapshots.
Additional program restoration uses tmux-resurrect's conservative defaults, not
restore-all.

## Verify

From the repository root, run `python3 -B tests/run.py common/tmux`.
Stow lifecycle tests use a temporary home and preserve synthetic plugin data;
they also check that existing configuration conflicts are not overwritten.
The suite starts disposable tmux servers on private sockets and removes TPM's
bootstrap only from its fixture. It inspects native options and bindings, not
real plugins, saved sessions, clipboard integration or visible true color.
Check those behaviors separately in an owner-approved isolated live session
using synthetic content only.
