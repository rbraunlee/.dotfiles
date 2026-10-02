-- nvim-treesitter, `main` branch (the rewrite).
--
-- Neovim 0.12 requires this branch; the frozen `master` branch explicitly
-- does not support 0.12. Note that `main` has no `configs.setup()` and no
-- `auto_install`: parsers are installed through `install()`, and highlighting
-- plus indentation are opted into per buffer.
return {
  "nvim-treesitter/nvim-treesitter",
  branch = "main",
  -- upstream: "This plugin does not support lazy-loading"
  lazy = false,
  build = ":TSUpdate",
  config = function()
    require("nvim-treesitter").setup({})

    local parsers = {
      "bash",
      "c",
      "html",
      "json",
      "lua",
      "markdown",
      -- markdown_inline is required for full markdown highlighting
      "markdown_inline",
      "python",
      -- the tree-sitter query language itself
      "query",
      "vim",
      "vimdoc",
    }

    local filetypes = { "bash", "c", "html", "json", "lua", "markdown", "python", "vim" }

    local langs = {
      bash = "bash",
      c = "c",
      html = "html",
      json = "json",
      lua = "lua",
      markdown = { "markdown", "markdown_inline" },
      python = "python",
      vim = "vim",
      vimdoc = "vimdoc",
    }

    -- Highlighting and indentation are per buffer, not global, so attach them
    -- to FileType rather than calling start() once at startup.
    vim.api.nvim_create_autocmd("FileType", {
      group = vim.api.nvim_create_augroup("nvim-treesitter", { clear = true }),
      pattern = filetypes,
      callback = function(args)
        vim.bo[args.buf].indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
        pcall(vim.treesitter.start, args.buf, langs)
      end,
    })

    -- get_installed() returns a list, not a set, so index it into one first.
    -- Passing no argument would merge the queries/ and parser/ directories,
    -- meaning a language with queries but no compiled .so would read as
    -- installed; 'parsers' filters to the real thing.
    local installed = {}
    for _, name in ipairs(require("nvim-treesitter").get_installed("parsers")) do
      installed[name] = true
    end

    local missing = {}
    for _, parser in ipairs(parsers) do
      if not installed[parser] then
        table.insert(missing, parser)
      end
    end

    if #missing > 0 then
      -- install() is asynchronous: it returns a task and yields while
      -- downloading and compiling. Blocking here would freeze startup on the
      -- first run, so let it finish in the background and pick up the current
      -- buffer once it has.
      require("nvim-treesitter").install(missing):await(function()
        vim.bo.indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
        pcall(vim.treesitter.start, 0, langs)
      end)
    end
  end,
}