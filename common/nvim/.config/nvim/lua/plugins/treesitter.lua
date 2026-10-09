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

    -- Filetypes and parser names are not interchangeable (notably sh and help).
    local languages = {
      bash = "bash",
      c = "c",
      help = "vimdoc",
      html = "html",
      json = "json",
      lua = "lua",
      markdown = "markdown", -- markdown_inline runs through injections
      python = "python",
      query = "query",
      sh = "bash",
      vim = "vim",
    }

    local treesitter = require("nvim-treesitter")
    local function attach(buf)
      if not vim.api.nvim_buf_is_valid(buf) or not vim.api.nvim_buf_is_loaded(buf) then
        return
      end
      local language = languages[vim.bo[buf].filetype]
      if not language then
        return
      end
      local installed = {}
      for _, name in ipairs(treesitter.get_installed("parsers")) do
        installed[name] = true
      end
      if not installed[language] then
        return
      end
      if pcall(vim.treesitter.start, buf, language)
        and vim.api.nvim_buf_is_valid(buf)
        and vim.api.nvim_buf_is_loaded(buf)
        and languages[vim.bo[buf].filetype] == language
      then
        vim.bo[buf].indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
      end
    end

    -- Highlighting and indentation are per buffer, not global, so attach them
    -- to FileType rather than calling start() once at startup.
    vim.api.nvim_create_autocmd("FileType", {
      group = vim.api.nvim_create_augroup("nvim-treesitter", { clear = true }),
      pattern = vim.tbl_keys(languages),
      callback = function(args)
        attach(args.buf)
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
      -- first run. Recheck each eligible buffer after completion rather than
      -- writing to whichever buffer happens to be current at that moment.
      treesitter.install(missing):await(function(err)
        if err then
          return
        end
        for _, buf in ipairs(vim.api.nvim_list_bufs()) do
          pcall(attach, buf)
        end
      end)
    end
  end,
}
