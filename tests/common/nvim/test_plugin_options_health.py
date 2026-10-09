"""Exercise plugin options and health in an isolated, plugin-free Neovim."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "common/nvim/.config/nvim"


class PluginOptionsHealth(unittest.TestCase):
    def run_nvim(self, setup, checks):
        with tempfile.TemporaryDirectory(prefix="nvim-health-test-", dir="/tmp/opencode") as directory:
            root = Path(directory)
            env = {"PATH": os.defpath}
            for name in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
                location = root / name
                location.mkdir()
                env[name] = str(location)
            env["NVIM_APPNAME"] = "health-test"
            env["NVIM_LOG_FILE"] = str(root / "nvim.log")
            script = root / "checks.lua"
            script.write_text(setup + "\n" + checks)
            result = subprocess.run(
                ["nvim", "--headless", "-u", "NONE", "--noplugin", "-i", "NONE", "-l", str(script)],
                cwd=root, env=env, capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_lazy_receives_checker_and_original_icons_in_both_font_modes(self):
        self.run_nvim("""
vim.fn.mkdir(vim.fn.stdpath('data') .. '/lazy/lazy.nvim', 'p')
local effective = {}
package.preload['lazy'] = function() return { setup = function(spec, opts)
  -- Pinned Lazy: a spec-bearing table is itself the complete options object.
  if spec.spec then opts = spec else opts = opts or {}; opts.spec = spec end
  table.insert(effective, opts)
end } end
""", """
for _, font in ipairs({true, false}) do
  vim.g.have_nerd_font = font
  dofile(""" + repr(str(CONFIG / "lua/config/lazy.lua")) + """ )
  local opts = effective[#effective]
  assert(#effective == (font and 1 or 2))
  assert(opts.spec[1].import == 'plugins' and opts.checker.enabled == true)
  assert(type(opts.ui) == 'table' and type(opts.ui.icons) == 'table', vim.inspect(opts))
  if font then
    assert(vim.tbl_isempty(opts.ui.icons), vim.inspect(opts.ui.icons))
  else
    local expected = { cmd = '⌘', config = '', event = '', ft = '', init = '⚙',
      keys = '', plugin = '', runtime = '󰍹', require = '', source = '󰈔',
      start = '', task = '', lazy = '󰒲' }
    assert(vim.deep_equal(opts.ui.icons, expected), vim.inspect(opts.ui.icons))
  end
end
""")

    def test_diffview_declares_plenary_as_a_lazy_dependency(self):
        self.run_nvim("", """
local spec = dofile(""" + repr(str(CONFIG / "lua/plugins/diffview.lua")) + """ )
assert(spec[1] == 'sindrets/diffview.nvim')
assert(vim.deep_equal(spec.dependencies, {'nvim-lua/plenary.nvim'}), vim.inspect(spec))
assert(spec.requires == nil, 'unsupported dependency field')
""")

    def test_health_import_is_silent_and_each_check_starts_exactly_one_report(self):
        self.run_nvim("""
local events = {}
vim.health = {}
for _, level in ipairs({'start', 'info', 'ok', 'warn', 'error'}) do
  vim.health[level] = function(msg) table.insert(events, {level, msg}) end
end
-- Fake every external provider: no diagnostic should invoke a host executable.
vim.fn.executable = function() return 1 end
vim.system = function() return {wait = function() return {code = 0, stdout = 'tree-sitter 0.26.1'} end} end
package.path = """ + repr(str(CONFIG / "lua/?.lua")) + """ .. ';' .. package.path
local health = require('health')
assert(#events == 0, vim.inspect(events))
""", """
health.check()
health.check()
local starts = 0
for _, event in ipairs(events) do
  if event[1] == 'start' then starts = starts + 1 end
end
assert(starts == 2, vim.inspect(events))
""")

    def test_locked_neovim_minimum_accepts_boundary_and_rejects_older_versions(self):
        self.run_nvim("""
local events = {}
vim.health = {}
for _, level in ipairs({'start', 'info', 'ok', 'warn', 'error'}) do
  vim.health[level] = function(msg) table.insert(events, {level, msg}) end
end
vim.fn.executable = function() return 1 end
vim.system = function() return {wait = function() return {code = 0, stdout = 'tree-sitter 0.26.1'} end} end
local original = vim.version
local current = {major = 0, minor = 11, patch = 9}
vim.version = setmetatable({cmp = original.cmp}, {__call = function() return current end})
local health = dofile(""" + repr(str(CONFIG / "lua/health.lua")) + """ )
local function has(level, text)
  for _, event in ipairs(events) do
    if event[1] == level and event[2]:find(text, 1, true) then return true end
  end
  return false
end
""", """
health.check()
assert(has('error', 'Neovim') and has('error', '0.12.0'), vim.inspect(events))
events = {}
current = {major = 0, minor = 12, patch = 0}
health.check()
assert(has('ok', 'Neovim') and not has('error', 'Neovim'), vim.inspect(events))
""")

    def test_tree_sitter_cli_is_required_at_locked_minimum(self):
        self.run_nvim("""
local events, version, available = {}, 'tree-sitter 0.26.0', true
vim.health = {}
for _, level in ipairs({'start', 'info', 'ok', 'warn', 'error'}) do
  vim.health[level] = function(msg) table.insert(events, {level, msg}) end
end
vim.fn.executable = function(exe) return (exe ~= 'tree-sitter' or available) and 1 or 0 end
vim.system = function(cmd)
  assert(vim.deep_equal(cmd, {'tree-sitter', '--version'}), vim.inspect(cmd))
  return {wait = function() return {code = 0, stdout = version} end}
end
local health = dofile(""" + repr(str(CONFIG / "lua/health.lua")) + """ )
local function has(level, text)
  for _, event in ipairs(events) do
    if event[1] == level and event[2]:find(text, 1, true) then return true end
  end
  return false
end
""", """
health.check()
assert(has('error', 'tree-sitter') and has('error', '0.26.1'), vim.inspect(events))
events, version = {}, 'tree-sitter 0.26.1'
health.check()
assert(has('ok', 'tree-sitter') and not has('error', 'tree-sitter'), vim.inspect(events))
events, available = {}, false
health.check()
assert(has('error', 'tree-sitter') and has('error', '0.26.1'), vim.inspect(events))
""")

    def test_required_tools_and_optional_integration_tools_are_distinguished(self):
        self.run_nvim("""
local events, available = {}, {['tree-sitter'] = true, gcc = true}
vim.health = {}
for _, level in ipairs({'start', 'info', 'ok', 'warn', 'error'}) do
  vim.health[level] = function(msg) table.insert(events, {level, msg}) end
end
vim.fn.executable = function(exe) return available[exe] and 1 or 0 end
vim.system = function(cmd)
  assert(vim.deep_equal(cmd, {'tree-sitter', '--version'}))
  return {wait = function() return {code = 0, stdout = 'tree-sitter 0.26.1'} end}
end
local health = dofile(""" + repr(str(CONFIG / "lua/health.lua")) + """ )
local function has(level, text)
  for _, event in ipairs(events) do
    if event[1] == level and event[2]:find(text, 1, true) then return true end
  end
  return false
end
""", """
health.check()
for _, exe in ipairs({'git', 'tar', 'curl'}) do
  assert(has('error', exe), exe .. ': ' .. vim.inspect(events))
end
assert(has('ok', 'gcc') and not has('error', 'compiler'), vim.inspect(events))
for _, exe in ipairs({'make', 'rg', 'unzip'}) do
  assert(has('warn', exe) and has('warn', 'optional'), exe .. ': ' .. vim.inspect(events))
end
assert(not has('error', 'edge') and not has('warn', 'edge'), vim.inspect(events))
events, available = {}, {git = true, tar = true, curl = true, ['tree-sitter'] = true}
health.check()
assert(has('error', 'C compiler'), vim.inspect(events))
""")

    def test_diagnostic_provider_failures_are_reported_without_aborting_other_checks(self):
        self.run_nvim("""
local events = {}
vim.health = {}
for _, level in ipairs({'start', 'info', 'ok', 'warn', 'error'}) do
  vim.health[level] = function(msg) table.insert(events, {level, msg}) end
end
vim.fn.executable = function() return 1 end
vim.system = function() error('CLI provider failed') end
vim.version = function() error('version provider failed') end
local uv = vim.uv or vim.loop
uv.os_uname = function() error('system provider failed') end
local health = dofile(""" + repr(str(CONFIG / "lua/health.lua")) + """ )
local function has(level, text)
  for _, event in ipairs(events) do
    if event[1] == level and event[2]:find(text, 1, true) then return true end
  end
  return false
end
""", """
health.check()
assert(has('error', 'system provider failed'), vim.inspect(events))
assert(has('error', 'version provider failed'), vim.inspect(events))
assert(has('error', 'CLI provider failed'), vim.inspect(events))
assert(has('ok', 'git') and has('ok', 'tar'), vim.inspect(events))
local starts = 0
for _, event in ipairs(events) do if event[1] == 'start' then starts = starts + 1 end end
assert(starts == 1, vim.inspect(events))
""")

    def test_failed_cli_version_comparison_does_not_hide_other_prerequisites(self):
        self.run_nvim("""
local events = {}
vim.health = {}
for _, level in ipairs({'start', 'info', 'ok', 'warn', 'error'}) do
  vim.health[level] = function(msg) table.insert(events, {level, msg}) end
end
vim.fn.executable = function() return 1 end
vim.system = function() return {wait = function()
  return {code = 0, stdout = 'tree-sitter 0.26.1'}
end} end
local health = dofile(""" + repr(str(CONFIG / "lua/health.lua")) + """ )
local original = vim.version.cmp
local calls = 0
vim.version.cmp = function(...)
  calls = calls + 1
  if calls == 2 then error('comparison failed') end
  return original(...)
end
""", """
health.check()
local cli_error, git_ok = false, false
for _, event in ipairs(events) do
  if event[1] == 'error' and event[2]:find('comparison failed', 1, true) then cli_error = true end
  if event[1] == 'ok' and event[2]:find('git', 1, true) then git_ok = true end
end
assert(cli_error and git_ok, vim.inspect(events))
""")


if __name__ == "__main__":
    unittest.main()
