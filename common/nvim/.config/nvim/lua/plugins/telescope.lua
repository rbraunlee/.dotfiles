return {
  -- Fuzzy Finder (files, lsp, etc)
  'nvim-telescope/telescope.nvim',
  event = 'VimEnter',
  branch = '0.1.x',
  dependencies = {
    'nvim-lua/plenary.nvim',
    { -- If encountering errors, see telescope-fzf-native README for install instructions
      'nvim-telescope/telescope-fzf-native.nvim',

      -- `build` is used to run some command when the plugin is installed/updated.
      -- This is only run then, not every time Neovim starts up.
      build = 'make',

      -- `cond` is a condition used to determine whether this plugin should be
      -- installed and loaded.
      cond = function()
        return vim.fn.executable 'make' == 1
      end,
    },
    { 'nvim-telescope/telescope-ui-select.nvim' },

    -- Useful for getting pretty icons, but requires a Nerd Font.
    { 'nvim-tree/nvim-web-devicons', enabled = vim.g.have_nerd_font },
  },
  config = function()
    -- Telescope is a fuzzy finder that comes with a lot of different things that
    -- it can fuzzy find! It's more than just a "file finder", it can search
    -- many different aspects of Neovim, your workspace, LSP, and more!
    --

    -- The easiest way to use telescope, is to start by doing something like:
    --  :Telescope help_tags
    --
    -- After running this command, a window will open up and you're able to
    -- type in the prompt window. You'll see a list of help_tags options and
    -- a corresponding preview of the help.
    --
    -- Two important keymaps to use while in telescope are:
    --  - Insert mode: <c-/>
    --  - Normal mode: ?
    --
    -- This opens a window that shows you all of the keymaps for the current
    -- telescope picker. This is really useful to discover what Telescope can
    -- do as well as how to actually do it!

    -- [[ Configure Telescope ]]
    -- See `:help telescope` and `:help telescope.setup()`
    require('telescope').setup {
      defaults = {
        preview = {
          -- Pinned Telescope 0.1.x still calls nvim-treesitter.parsers.ft_to_lang
          -- in its preview highlighter; the pinned main rewrite removed it.
          -- Keep the normal file preview and regex fallback, then attach via
          -- Neovim's native parser API after Telescope has filled the buffer.
          treesitter = false,
          filetype_hook = function(_, buf, opts)
            opts.preview.treesitter = false
            local callback = opts.callback
            opts.callback = function(preview_buf, ...)
              if callback then callback(preview_buf, ...) end
              local ft = opts.ft
              if not ft or ft == '' then return end
              vim.schedule(function()
                if not vim.api.nvim_buf_is_valid(preview_buf) then return end
                local lang = vim.treesitter.language.get_lang(ft) or ft
                if #vim.api.nvim_get_runtime_file('parser/' .. lang .. '.so', false) == 0 then return end
                if pcall(vim.treesitter.start, preview_buf, lang)
                  and vim.api.nvim_buf_is_valid(preview_buf)
                then
                  -- The pinned maker installs regex syntax after its callback.
                  vim.bo[preview_buf].syntax = ''
                end
              end)
            end
            return true
          end,
        },
      },
      -- You can put your default mappings / updates / etc. in here
      --  All the info you're looking for is in `:help telescope.setup()`
      --
      -- defaults = {
      --   mappings = {
      --     i = { ['<c-enter>'] = 'to_fuzzy_refine' },
      --   },
      -- },
      -- pickers = {}
      extensions = {
        ['ui-select'] = {
          require('telescope.themes').get_dropdown(),
        },
      },
    }

    -- Enable telescope extensions, if they are installed
    pcall(require('telescope').load_extension, 'fzf')
    pcall(require('telescope').load_extension, 'ui-select')

    -- See `:help telescope.builtin`
    local builtin = require 'telescope.builtin'
    vim.keymap.set('n', '<leader>sh', builtin.help_tags, { desc = '[S]earch [H]elp' })
    vim.keymap.set('n', '<leader>sk', builtin.keymaps, { desc = '[S]earch [K]eymaps' })
    vim.keymap.set('n', '<leader>sf', builtin.find_files, { desc = '[S]earch [F]iles' })
    -- Modify find_files to only search current buffer
    -- vim.keymap.set('n', '<leader>sf', function()
    --   builtin.find_files {
    --     cwd = vim.fn.expand '%p:h',
    --   }
    -- end, { desc = '[S]earch [F]iles' })
    vim.keymap.set('n', '<leader>ss', builtin.builtin, { desc = '[S]earch [S]elect Telescope' })
    vim.keymap.set('n', '<leader>sw', builtin.grep_string, { desc = '[S]earch current [W]ord' })
    vim.keymap.set('n', '<leader>sg', builtin.live_grep, { desc = '[S]earch by [G]rep' })
    vim.keymap.set('n', '<leader>sd', builtin.diagnostics, { desc = '[S]earch [D]iagnostics' })
    vim.keymap.set('n', '<leader>sr', builtin.resume, { desc = '[S]earch [R]esume' })
    vim.keymap.set('n', '<leader>s.', builtin.oldfiles, { desc = '[S]earch Recent Files ("." for repeat)' })
    vim.keymap.set('n', '<leader><leader>', builtin.buffers, { desc = '[ ] Find existing buffers' })

    -- Slightly advanced example of overriding default behavior and theme
    vim.keymap.set('n', '<leader>/', function()
      -- You can pass additional configuration to telescope to change theme, layout, etc.
      builtin.current_buffer_fuzzy_find(require('telescope.themes').get_dropdown {
        winblend = 10,
        previewer = false,
      })
    end, { desc = '[/] Fuzzily search in current buffer' })

    -- Also possible to pass additional configuration options.
    --  See `:help telescope.builtin.live_grep()` for information about particular keys
    vim.keymap.set('n', '<leader>s/', function()
      builtin.live_grep {
        grep_open_files = true,
        prompt_title = 'Live Grep in Open Files',
      }
    end, { desc = '[S]earch [/] in Open Files' })

    -- A folded config directory resolves directly into the package; with
    -- individual-file Stow links the init file provides the same anchor.
    local function dotfiles_root(config)
      local suffix = '/common/nvim/.config/nvim'
      for _, source in ipairs { config, config .. '/init.lua' } do
        local resolved = vim.uv.fs_realpath(source)
        local directory = source == config and resolved or (resolved and vim.fs.dirname(resolved))
        if directory and directory:sub(-#suffix) == suffix then
          local root = directory:sub(1, -#suffix - 1)
          if vim.uv.fs_stat(root .. '/.git') then
            return root
          end
        end
      end
    end

    -- Keep the active config path for individual links. Telescope's `follow`
    -- makes linked files visible; its normal ignore rules remain in force.
    vim.keymap.set('n', '<leader>sn', function()
      builtin.find_files { cwd = vim.fn.stdpath 'config', hidden = true, follow = true }
    end, { desc = '[S]earch [N]eovim files' })
    -- Search only environment-group packages, never HOME or repository metadata.
    vim.keymap.set('n', '<leader>sc', function()
      local root = dotfiles_root(vim.fn.stdpath 'config')
      if not root then
        vim.notify('Cannot locate dotfiles repository from active Neovim config', vim.log.levels.WARN)
        return
      end
      local groups = {}
      for _, group in ipairs { 'common', 'linux', 'macos' } do
        local path = root .. '/' .. group
        local stat = vim.uv.fs_stat(path)
        if stat and stat.type == 'directory' then
          table.insert(groups, path)
        end
      end
      if #groups == 0 then
        vim.notify('No environment-group packages found in dotfiles repository: ' .. root, vim.log.levels.WARN)
        return
      end
      builtin.find_files { cwd = root, search_dirs = groups, hidden = true }
    end, { desc = '[S]earch [C]onfiguration files' })
  end,
}
