vim.keymap.set('n', '<Esc>', '<cmd>nohlsearch<CR>')

-- Exit Document
vim.keymap.set('n', '<leader>ef', vim.cmd.Ex, { desc = 'Exit file' })
-- Diagnostic keymaps
vim.keymap.set('n', '[d', vim.diagnostic.goto_prev, { desc = 'Go to previous [D]iagnostic message' })
vim.keymap.set('n', ']d', vim.diagnostic.goto_next, { desc = 'Go to next [D]iagnostic message' })
vim.keymap.set('n', '<leader>e', vim.diagnostic.open_float, { desc = 'Show diagnostic [E]rror messages' })
vim.keymap.set('n', '<leader>q', vim.diagnostic.setloclist, { desc = 'Open diagnostic [Q]uickfix list' })

-- Enforce hjkl in normal mode.
-- vim.notify with a timeout rather than <cmd>echo: echo leaves its message on
-- the command line indefinitely, notify clears itself after 1000ms.
-- noremap is vim.keymap.set's default, stated explicitly because these shadow a
-- key the user may have mapped themselves.
local function nudge(msg)
    vim.notify(msg, vim.log.levels.INFO, { timeout = 1000 })
end
vim.keymap.set('n', '<left>',  function() nudge('Use h to move') end, { noremap = true })
vim.keymap.set('n', '<right>', function() nudge('Use l to move') end, { noremap = true })
vim.keymap.set('n', '<up>',    function() nudge('Use k to move') end, { noremap = true })
vim.keymap.set('n', '<down>',  function() nudge('Use j to move') end, { noremap = true })

-- Keybinds to make split navigation easier.
--  Use CTRL+<hjkl> to switch between windows
-- Disabled for tmux navigator
--  See `:help wincmd` for a list of all window commands
-- vim.keymap.set('n', '<C-h>', '<C-w><C-h>', { desc = 'Move focus to the left window' })
-- vim.keymap.set('n', '<C-j>', '<C-w><C-l>', { desc = 'Move focus to the right window' })
-- vim.keymap.set('n', '<C-k>', '<C-w><C-j>', { desc = 'Move focus to the lower window' })
-- vim.keymap.set('n', '<C-l>', '<C-w><C-k>', { desc = 'Move focus to the upper window' })
