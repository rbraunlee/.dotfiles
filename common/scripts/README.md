# Personal commands

Reusable executable shell scripts live in `.local/bin/` in this Stow package.
Use extensionless command names (`focus`, `notetaker`), a shell shebang,
and executable permissions. Keep app-specific helpers with their app package.
Keep preferences in `~/.config/<command>/` and runtime state in
`~/.local/state/<command>/`, outside Git.

## Focus startup (Linux)

Requires Bash, Ghostty, tmux, realpath and util-linux flock.

```sh
cd ~/.dotfiles
stow -n -v --no-folding -t ~ -d common scripts
stow --no-folding -t ~ -d common scripts
focus --set /absolute/path/to/project
focus --now
```

The Hyprland startup hook calls `focus --daily`. Until a project is selected,
it does nothing. The first successful launch each local calendar day opens one
Ghostty window with a `focus` tmux session in that project. Later logins skip it.
`focus --now` bypasses the day check. A lock prevents simultaneous launches.
The date is recorded inside the terminal after the session exists, allowing a
failed terminal launch to retry. This does not close other applications.

Focus uses a separate tmux server (`tmux -L focus`) with default tmux settings,
so automatic session restoration cannot populate the focus session. Detaching
leaves the session alive; subsequent launches reattach. After changing projects,
end the old session to start fresh in the selected directory.

Remove `~/.config/focus/project` to disable automatic focus startup.
## Note-taking scripts

`notetaker` is the original daily-note command. Its Linux vault path is
`$HOME/ssd/obsidian_vault/Daily`, matching the installed Obsidian vault.
The macOS variant lives in `macos/scripts/.local/bin/notetaker-macos` and retains
its mounted-volume check and Homebrew Neovim path. Install that variant with
`stow --no-folding -t ~ -d macos scripts` on macOS.

## Leaving focus

Press **Ctrl+B**, release, then **D** to detach. The tmux session stays alive;
`focus --now` reconnects. Running `exit` in the final pane ends the session.
Detaching does not save across a reboot: this private server deliberately uses
default settings and does not load tmux-resurrect or tmux-continuum.
