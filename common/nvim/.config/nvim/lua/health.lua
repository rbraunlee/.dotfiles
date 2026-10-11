--[[
--
-- This file is not required for your own configuration,
-- but helps people determine if their system is setup correctly.
--
--]]

local check_version = function()
  local verstr = string.format('%s.%s.%s', vim.version().major, vim.version().minor, vim.version().patch)
  if not vim.version.cmp then
    vim.health.error(string.format("Neovim '%s' cannot be compared; requires >=0.12.0", verstr))
    return
  end

  if vim.version.cmp(vim.version(), { 0, 12, 0 }) >= 0 then
    vim.health.ok(string.format("Neovim version is: '%s'", verstr))
  else
    vim.health.error(string.format("Neovim '%s' is too old; requires >=0.12.0", verstr))
  end
end

local check_tree_sitter_cli = function()
  if vim.fn.executable('tree-sitter') == 1 then
    local result = vim.system({ 'tree-sitter', '--version' }, { text = true }):wait()
    local major, minor, patch = (result.stdout or ''):match('tree%-sitter%s+(%d+)%.(%d+)%.(%d+)')
    if result.code == 0 and major and vim.version.cmp(
      { tonumber(major), tonumber(minor), tonumber(patch) }, { 0, 26, 1 }) >= 0 then
      vim.health.ok(string.format('tree-sitter CLI %s.%s.%s (requires >=0.26.1)', major, minor, patch))
    else
      vim.health.error('tree-sitter CLI requires >=0.26.1 (check `tree-sitter --version`)')
    end
  else
    vim.health.error('Missing tree-sitter CLI (requires >=0.26.1)')
  end
end

local check_external_reqs = function()
  for _, exe in ipairs { 'git', 'tar', 'curl' } do
    if vim.fn.executable(exe) == 1 then
      vim.health.ok('Found required executable: ' .. exe)
    else
      vim.health.error('Missing required executable: ' .. exe)
    end
  end

  local compiler
  for _, exe in ipairs { 'cc', 'gcc', 'clang' } do
    if vim.fn.executable(exe) == 1 then
      compiler = exe
      break
    end
  end
  if compiler then
    vim.health.ok('Found C compiler: ' .. compiler)
  else
    vim.health.error('Missing C compiler (cc, gcc or clang) for Tree-sitter parsers')
  end

  for _, exe in ipairs { 'make', 'rg', 'unzip' } do
    if vim.fn.executable(exe) == 1 then
      vim.health.ok('Found optional executable: ' .. exe)
    else
      vim.health.warn('Missing optional executable: ' .. exe)
    end
  end
end

return {
  check = function()
    vim.health.start 'health checker nvim'

    vim.health.info [[NOTE: Not every warning is a 'must-fix' in `:checkhealth`
    Fix only warnings for plugins and languages you intend to use.
    Mason will give warnings for languages that are not installed.
    You do not need to install, unless you want to use those languages!]]

    local uv = vim.uv or vim.loop
    local system_ok, system = pcall(uv.os_uname)
    if system_ok then
      vim.health.info('System Information: ' .. vim.inspect(system))
    else
      vim.health.error('Error checking system information: ' .. tostring(system))
    end

    local success, err = pcall(check_version)
    if not success then
      vim.health.error('Error checking version: ' .. tostring(err))
    end

    success, err = pcall(check_tree_sitter_cli)
    if not success then
      vim.health.error('Error checking tree-sitter CLI: ' .. tostring(err))
    end

    success, err = pcall(check_external_reqs)
    if not success then
      vim.health.error('Error checking external requirements: ' .. tostring(err))
    end
  end,
}
