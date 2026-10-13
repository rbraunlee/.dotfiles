-- One native terminal per editor instance; no OpenCode API or plugin dependency.
local M = {}
local terminal

local function live()
  return terminal and vim.api.nvim_buf_is_valid(terminal)
    and vim.fn.jobwait({ vim.b[terminal].terminal_job_id or -1 }, 0)[1] == -1
end

function M.toggle()
  if live() then
    local windows = vim.fn.win_findbuf(terminal)
    if #windows > 0 then
      local window = windows[1]
      if vim.api.nvim_win_is_valid(window) then
        vim.api.nvim_win_close(window, false)
        return
      end
    end
  else
    -- A finished job may still be displayed. Remove only its window, not the
    -- source window or the terminal buffer the user may want to inspect.
    if terminal and vim.api.nvim_buf_is_valid(terminal) and #vim.api.nvim_list_wins() > 1 then
      for _, window in ipairs(vim.fn.win_findbuf(terminal)) do
        if vim.api.nvim_win_is_valid(window) and #vim.api.nvim_list_wins() > 1 then
          vim.api.nvim_win_close(window, false)
        end
      end
    end
    terminal = nil
  end

  local launching = not terminal
  if launching and vim.fn.executable('opencode') ~= 1 then
    vim.notify('OpenCode terminal: install opencode and ensure it is on PATH', vim.log.levels.ERROR)
    return
  end

  local cwd = vim.fn.getcwd(0, 0)
  local source = vim.api.nvim_get_current_win()
  local ok, err = pcall(function()
    vim.cmd('botright vsplit')
    if launching then
      vim.cmd('enew')
      vim.bo.bufhidden = 'hide'
      local job = vim.fn.termopen({ 'opencode' }, { cwd = cwd })
      if job <= 0 then error('terminal job could not start') end
      terminal = vim.api.nvim_get_current_buf()
    else
      vim.api.nvim_win_set_buf(0, terminal)
    end
    vim.cmd('startinsert')
  end)
  if not ok then
    if vim.api.nvim_win_is_valid(source) and vim.api.nvim_get_current_win() ~= source then
      vim.api.nvim_win_close(0, true)
    end
    terminal = nil
    vim.notify('OpenCode terminal: launch failed (' .. tostring(err)
      .. '). Check opencode on PATH and the project directory.', vim.log.levels.ERROR)
  end
end

return M
