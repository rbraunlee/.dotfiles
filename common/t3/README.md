# T3 Code

T3 Code's integrated terminal already runs `$SHELL`, so the `zsh` and
`starship` packages apply there unchanged. Ghostty's config does not: T3 renders
its own terminal. This package carries the Ghostty `Gruvbox Material` palette
over as a T3 theme.

## Install

```bash
stow -n -v --no-folding -t ~ -d common t3
stow --no-folding -t ~ -d common t3
t3 theme set ~/.config/t3/themes/gruvbox-material.json
```

`t3` lives in `~/.t3/bin`. `theme set <path>` copies the file into
`~/.t3/userdata/themes/` and switches every connected client to it. T3 skips
symlinked files in that directory, which is why the theme is stowed to
`~/.config/t3` and published from there. **Re-run `theme set` after editing the
JSON**; the published copy does not follow the repository.

`t3 theme clear` removes the environment theme; clients keep what they have.

## Theme

`canvas` and `accent` derive the whole app palette, so the theme retints T3's
interface, not just the terminal. The generator tints surfaces toward the
accent, which turns the sidebar and message bubbles brown with a yellow
accent; the surface, border and text keys pin them to Gruvbox Material's
neutral greys instead. The `terminal*` and `ansi*` keys come from
`/usr/share/ghostty/themes/Gruvbox Material`; `accent` is Gruvbox Material's
yellow.

## Font

A theme cannot set fonts. Set them in T3's settings to match Ghostty; they are
stored per client in `~/.t3/userdata/client-settings.json`:

- Terminal font family: `ComicShannsMono Nerd Font Mono`
- Terminal font size: `14`

## Not covered

Ghostty keybindings have no T3 equivalent. T3's own terminal bindings
(`terminal.toggle`, `terminal.split`, …) are in `~/.t3/userdata/keybindings.json`.
