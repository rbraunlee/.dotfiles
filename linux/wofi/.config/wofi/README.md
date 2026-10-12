# Wofi style evidence and owner visual QA

This package uses the installed Wofi 1.5.3 stylesheet contract. The installed
`wofi(5)` manual recommends `#entry:selected` over `#selected` for selected
entries; `:focus` is a different state. The installed `wofi(7)` WIDGET LAYOUT
lists `#scroll`, `#inner-box` and `#entry` by name, but no `#list` ID. Its
secondary-action `list` node is *unnamed* (and this config has `no_actions=true`),
so `#list { margin: 0; padding: 0; }` was removed, without moving those
declarations elsewhere. This is an installed-version **documented widget-tree**
decision, not runtime inspection of every possible widget or future versions.

The existing blue `#458588` and foreground `#ebdbb2` declarations now target
`#entry:selected`, after the even-row rule. Both selectors have the same CSS
specificity (one ID and one pseudo-class), so the later selected rule takes
precedence for the selected even row. The entry's padding, rounding and margins,
and the scroll rule, remain as before. Automated tests check declarations,
unchanged config and native GTK3 CSS-provider syntax with no display; they do
**not** establish actual colors, keyboard/mouse behavior, or pixel layout in Wofi.

## Owner visual checklist (separate, only when approved)

Use owner-approved synthetic dmenu entries rather than real desktop entries or
`drun` app launches. Do not use live desktop interaction as an automated check.

- [ ] Initial selected entry is blue with readable text while search input has focus;
      a focused but unselected entry is not blue from this stylesheet.
- [ ] Arrow-key navigation moves the blue highlight to the selected target.
- [ ] Typing a filter keeps the visible selected match highlighted, including
      after the list changes.
- [ ] Mouse selection highlights the selected entry and does not leave an old
      entry with a focus-only blue highlight.
- [ ] Alternating rows retain their dark even-row backgrounds when unselected;
      the selected even row is blue.
- [ ] Entry spacing, rounded corners and launcher dimensions still look familiar.
- [ ] With enough synthetic entries to scroll, scroll spacing and selection remain
      usable. No real applications need to be launched to verify the appearance.
