-- Set to false if you have no Nerd Font installed.
-- Must come before config.lazy: lazy.setup() reads this while choosing its icon
-- set, so assigning it afterwards silently selects the generic unicode glyphs.
vim.g.have_nerd_font = true

require 'config.lazy'
require 'config.keymaps'
require 'config.vimopt'
require 'config.autocmd'

-- Configure netrw
-- remove the banner
vim.g.netrw_banner = 0
-- style of netrw
vim.g.netrw_liststyle = 3

-- require('avante_lib').load()
