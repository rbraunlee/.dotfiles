"""Exercise the configured preview hook against the pinned Telescope callback order."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


PLUGIN = Path(__file__).resolve().parents[3] / "common/nvim/.config/nvim/lua/plugins/telescope.lua"


class TelescopePreview(unittest.TestCase):
    def run_nvim(self, checks):
        with tempfile.TemporaryDirectory(prefix="nvim-preview-test-") as directory:
            root = Path(directory)
            script = root / "test.lua"
            script.write_text("""
local setup
package.preload['telescope'] = function() return {
  setup = function(opts) setup = opts end, load_extension = function() end,
} end
package.preload['telescope.themes'] = function() return {get_dropdown = function() return {} end} end
package.preload['telescope.builtin'] = function() return setmetatable({}, {
  __index = function() return function() end end,
}) end
local spec = dofile(""" + repr(str(PLUGIN)) + """ )
spec.config()
assert(setup.defaults.previewer ~= false and setup.defaults.preview ~= false,
  'normal preview windows must stay enabled')
-- Pinned Telescope 0.1.x file_maker: filetype_hook before I/O; callback
-- before highlighter; ts_highlighter uses obsolete ft_to_lang on main TS.
local preview = setup.defaults and setup.defaults.preview or { treesitter = true }
local pending = {}
local started = {}
local available = { lua = true }
local legacy_calls = 0
local parser_module = {} -- pinned main rewrite does not expose ft_to_lang
vim.treesitter.language.get_lang = function(ft) return ft end
vim.api.nvim_get_runtime_file = function(path)
  return available[path:match('^parser/(.-)%.so$')] and {path} or {}
end
vim.treesitter.start = function(buf, lang)
  assert(vim.api.nvim_buf_is_valid(buf) and available[lang], 'native parser missing')
  table.insert(started, {buf, lang})
end
local function make_preview(ft)
  local buf = vim.api.nvim_create_buf(false, true)
  local opts = {ft = ft, preview = vim.deepcopy(preview), callback = function(b)
    assert(b == buf)
    table.insert(pending, 'original callback')
  end}
  -- Telescope invokes the documented hook before the async file read.
  if opts.preview.filetype_hook then assert(opts.preview.filetype_hook('example.' .. ft, buf, opts) == true) end
  -- This is the pinned file_maker scheduled callback order; `ft_to_lang` is
  -- deliberately absent, so enabling its old TS path reproduces live QA.
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, {'preview text'})
  opts.callback(buf)
  -- Pinned utils.highlighter resolves falsy per-preview treesitter back to
  -- conf.preview.treesitter, so both must opt out of its legacy path.
  local ts_enabled = opts.preview.treesitter or preview.treesitter ~= false
  if ts_enabled then
    legacy_calls = legacy_calls + 1
    parser_module.ft_to_lang(ft)
  else
    vim.bo[buf].syntax = ft -- Telescope regex_highlighter fallback
  end
  vim.wait(200, function() return #pending > 1 end, 1)
  return buf
end
""" + checks)
            env = {"PATH": os.defpath}
            for name in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
                location = root / name
                location.mkdir()
                env[name] = str(location)
            env["NVIM_APPNAME"] = "preview-test"
            env["NVIM_LOG_FILE"] = str(root / "nvim.log")
            result = subprocess.run(
                ["nvim", "--headless", "-u", "NONE", "--noplugin", "-i", "NONE", "-l", str(script)],
                cwd=root, env=env, capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_preview_uses_native_parser_without_legacy_api_and_keeps_syntax_fallback(self):
        self.run_nvim("""
local present = make_preview('lua')
assert(#started == 1 and started[1][1] == present and started[1][2] == 'lua')
assert(vim.bo[present].syntax == '', 'native preview should not overlay regex syntax')
available.lua = nil
local missing = make_preview('lua')
assert(#started == 1 and vim.bo[missing].syntax == 'lua', 'missing parser should keep syntax')
assert(#pending == 2 and legacy_calls == 0, 'preview callback lost or legacy API used')
assert(parser_module.ft_to_lang == nil, 'must not add a compatibility global')
""")

    def test_deleted_preview_and_failed_native_parser_keep_safe_fallback(self):
        self.run_nvim("""
vim.treesitter.start = function() error('bad parser library') end
local failed = make_preview('lua')
assert(vim.bo[failed].syntax == 'lua' and #started == 0)
-- Asynchronous hooks can race with picker teardown; a deleted preview is safe.
local hook = preview.filetype_hook
local deleted = vim.api.nvim_create_buf(false, true)
local opts = {ft = 'lua', preview = {treesitter = true}, callback = function() end}
assert(hook('example.lua', deleted, opts))
vim.api.nvim_buf_delete(deleted, {force = true})
opts.callback(deleted)
vim.wait(100, function() return false end, 1)
assert(#started == 0 and #pending == 1)
""")

    def test_reused_preview_drops_stale_scheduled_attachment(self):
        self.run_nvim("""
local scheduled = {}
vim.schedule = function(fn) table.insert(scheduled, fn) end
available.python = true
local buf = vim.api.nvim_create_buf(false, true)
local hook = preview.filetype_hook
local function select(ft)
  local opts = {ft = ft, preview = {treesitter = true}, callback = function(b) assert(b == buf) end}
  assert(hook('example.' .. ft, buf, opts))
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, {ft .. ' preview'})
  opts.callback(buf)
  vim.bo[buf].syntax = ft -- pinned highlighter follows the callback
end
select('lua')
select('python')
assert(#scheduled == 2)
for _, fn in ipairs(scheduled) do fn() end
assert(#started == 1 and started[1][1] == buf and started[1][2] == 'python', vim.inspect(started))
assert(vim.bo[buf].syntax == '', 'current parser should replace regex fallback')
assert(vim.api.nvim_buf_get_lines(buf, 0, -1, false)[1] == 'python preview')
""")

    def test_preview_provider_failure_retains_regex_syntax_without_callback_error(self):
        self.run_nvim("""
local scheduled_errors = {}
vim.schedule = function(fn)
  local ok, err = pcall(fn)
  if not ok then table.insert(scheduled_errors, err) end
end
vim.treesitter.language.get_lang = function() error('unavailable filetype provider') end
local buf = make_preview('lua')
assert(#started == 0 and vim.bo[buf].syntax == 'lua')
vim.treesitter.language.get_lang = function(ft) return ft end
vim.api.nvim_get_runtime_file = function() error('unavailable parser provider') end
local other = make_preview('lua')
assert(#started == 0 and vim.bo[other].syntax == 'lua')
vim.api.nvim_get_runtime_file = function() return nil end
local invalid = make_preview('lua')
assert(#started == 0 and vim.bo[invalid].syntax == 'lua')
assert(#pending == 3 and legacy_calls == 0)
assert(#scheduled_errors == 0, vim.inspect(scheduled_errors))
""")


if __name__ == "__main__":
    unittest.main()
