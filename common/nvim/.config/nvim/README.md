# Neovim configuration (`common/nvim`)

This is the modular Neovim configuration in this dotfiles repository, adapted
from [Kickstart.nvim](https://github.com/nvim-lua/kickstart.nvim) and
[BraunRudolf/kickstart.nvim](https://github.com/BraunRudolf/kickstart.nvim).
`init.lua` loads `lua/config/` and the plugin specifications in `lua/plugins/`;
it is not a standalone, single-file Kickstart clone. See [LICENSE.md](LICENSE.md)
for the retained MIT license.

## Deploy with GNU Stow

Follow the [repository setup and Stow instructions](../../../../README.md) for
cloning the *dotfiles repository* and checking for conflicts. From the repository
root, this package's dry run is `stow -n -v -t ~ -d common nvim`; after resolving
conflicts, the corresponding application is `stow -t ~ -d common nvim`.
The package mirrors `$HOME`: its `.config/nvim/` belongs at `~/.config/nvim/`.
Stow may fold that directory into a symlink or link its files individually.
These paths assume Neovim uses the default XDG config location; a different
`XDG_CONFIG_HOME` needs a matching deployment target. Do not clone Kickstart
directly into `~/.config/nvim` on top of this Stow package or delete existing
Neovim configuration, plugin data or caches to install it. Resolve any existing
config/link conflicts deliberately, keeping your own data.

## Prerequisites and first launch

- Use **Neovim >=0.12.0** (the locked `nvim-treesitter` `main` rewrite and
  `vim.lsp.config` need it), GNU Stow for deployment and `git` for plugin
  bootstrap. The first normal launch bootstraps lazy.nvim and its locked plugins
  if absent; that requires network access. Inspect status with `:Lazy`.
- Parser installation needs **tree-sitter CLI >=0.26.1** (`tree-sitter` on PATH),
  `tar`, `curl` and a C compiler (`cc`, `gcc` or `clang`). The config requests
  its configured parsers asynchronously when missing; installation is not a
  synchronous startup guarantee. Parsers include `bash`, `c`, `html`, `json`,
  `lua`, `markdown`, `markdown_inline`, `python`, `query`, `vim` and `vimdoc`.
  Markdown inline highlighting uses injections. Eligible open buffers are
  rechecked after a successful install; without a working parser their previous
  indentation stays in place. `:TSUpdate` is the configured plugin build/update
  action, not a substitute for the CLI/compiler prerequisites.
- `make` is needed to build the optional Telescope fzf-native extension; `rg`
  (ripgrep) is needed for Telescope grep and useful for file searches; `unzip`
  is an optional tool. A Nerd Font is optional for icons; `init.lua` currently
  sets `vim.g.have_nerd_font = true` before Lazy setup, so set it to `false`
  there if you do not have one. Language-specific servers/tools may need their
  own runtimes (for example, npm for JS/TS tooling).
- The config sets `clipboard=unnamedplus`: install an OS-appropriate Neovim
  clipboard provider and ensure it is available in your editor session (for
  example `wl-copy`/`wl-paste` on Wayland, `xclip`/`xsel` on X11, or `pbcopy`
  on macOS). A headless test does not prove clipboard integration. Check your
  active provider with `:checkhealth provider` if copy/paste fails.

The package health module reports on invocation of `:checkhealth`, not when
required: it checks Neovim and CLI minimums, `git`/`tar`/`curl`/compiler, and
warns for optional `make`/`rg`/`unzip`. Other health warnings can be specific
to languages/plugins you do not use; don't treat every warning as a required
installation. Mason's `ensure_installed` list provisions configured language
servers (`lua_ls`, `pyright`, `bashls`, `dockerls`, `marksman`, `jsonls`), **not**
Conform's formatter executables. Provision `stylua` for Lua, `isort` then
`black` for Python, and `prettierd` and/or `prettier` for Markdown and JSON
separately on PATH if you use those formats. The configured lists run available
formatters in order (not as a first-available fallback). Existing on-save/manual
formatting and Black's 100-column option are unchanged. The Ollama
integration separately requires a running local service and its configured
`codellama` model if you use it.

## Searching and checking behavior

`<leader>sn` finds files in the *active* Neovim config, following Stow links.
`<leader>sc` finds configuration across the repository's `common`, `linux` and
`macos` package trees, resolving the checkout via the active config rather than
the current working directory or a fixed clone path. It warns rather than
searching all of HOME if that repository cannot be identified. Both pickers
retain normal ignore behavior; hidden files are included, not ignored files.
Tree-sitter highlighting and indentation attach per eligible buffer/filetype
when the matching parser is available (including `sh` via `bash`, `help` via
`vimdoc` and `query`); missing or failed parsers do not force indentation.

The package regression command, run from the repository root, is
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/common/nvim -v`.
It exercises the configuration in isolated headless Neovim with fake plugin,
parser, search and health providers; it neither installs plugins/parsers nor
proves real parser rendering, clipboard transfer, graphical UI or macOS behavior.
Those require a separately approved live check in the target environment,
including Markdown inline injections and search in an actual Stow deployment.

## Upstream references

The original [Kickstart getting-started video](https://youtu.be/m8C0Cq9Uv9o)
and discussions on [splitting the configuration](https://github.com/nvim-lua/kickstart.nvim/issues/218)
and [multi-file layouts](https://github.com/nvim-lua/kickstart.nvim/pull/473)
and the [Kickstart modular example](https://github.com/dam9000/kickstart-modular.nvim)
remain useful background, but their standalone clone/install recipes are **not**
instructions for this Stow package. For an isolated experiment with another
Neovim config, see [`NVIM_APPNAME`](https://neovim.io/doc/user/starting.html#%24NVIM_APPNAME)
rather than replacing this package or removing its data.
