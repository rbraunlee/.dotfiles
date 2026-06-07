return {
  'TimUntersberger/neogit',
  dependencies = {
    'nvim-lua/plenary.nvim',
    'sindrets/diffview.nvim',
  },
  config = function()
    require('neogit').setup {
      integrations = {
        diffview = true, -- Integrate with diffview.nvim
      },
    }
    vim.keymap.set('n', '<leader>gs', vim.cmd.Neogit, { desc = '[G]it[S]tatus' })
  end,
}
