"""Exercise the real plugin callback in isolated, plugin-free headless Neovim."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / "common/nvim/.config/nvim/lua/plugins/treesitter.lua"


class TreesitterAttachment(unittest.TestCase):
    def run_nvim(self, checks):
        with tempfile.TemporaryDirectory(prefix="nvim-treesitter-test-", dir="/tmp/opencode") as directory:
            root = Path(directory)
            script = root / "test.lua"
            script.write_text(
                """
local installed = { bash = true, c = true, html = true, json = true,
  lua = true, markdown = true, markdown_inline = true, python = true,
  query = true, vim = true, vimdoc = true }
local started, pending, requests = {}, nil, {}
local plugin = {
  setup = function() end,
  get_installed = function(kind)
    assert(kind == 'parsers', 'must check compiled parsers')
    local names = {}
    for name, available in pairs(installed) do
      if available then table.insert(names, name) end
    end
    return names
  end,
  install = function(names)
    requests = names
    return { await = function(_, cb) pending = cb end }
  end,
}
package.preload['nvim-treesitter'] = function() return plugin end
vim.treesitter.start = function(buf, lang)
  assert(type(buf) == 'number' and buf ~= 0, 'explicit buffer required')
  assert(type(lang) == 'string', 'native start expects one language')
  assert(vim.api.nvim_buf_is_valid(buf), 'deleted buffer')
  assert(installed[lang], 'parser unavailable: ' .. lang)
  table.insert(started, { buf = buf, lang = lang })
end
local spec = dofile(""" + repr(str(PLUGIN)) + """ )
local function buffer(ft, indent)
  local buf = vim.api.nvim_create_buf(true, false)
  vim.bo[buf].indentexpr = indent or 'existing_indent()'
  vim.bo[buf].filetype = ft
  return buf
end
local function attach() spec.config() end
"""
                + checks
            )
            env = os.environ.copy()
            for name in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
                location = root / name
                location.mkdir()
                env[name] = str(location)
            env["NVIM_APPNAME"] = "treesitter-test"
            env["NVIM_LOG_FILE"] = str(root / "nvim.log")
            result = subprocess.run(
                ["nvim", "--headless", "-u", "NONE", "--noplugin", "-i", "NONE", "-l", str(script)],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_native_attachment_preserves_markdown_injections_and_indentation(self):
        self.run_nvim("""
attach()
local buf = buffer('markdown')
assert(#started == 1 and started[1].buf == buf and started[1].lang == 'markdown', vim.inspect(started))
assert(vim.bo[buf].indentexpr == "v:lua.require'nvim-treesitter'.indentexpr()")
""")

    def test_all_supported_filetypes_use_their_parser_without_touching_unsupported_buffers(self):
        self.run_nvim("""
attach()
local expected = { bash = 'bash', sh = 'bash', c = 'c', html = 'html',
  json = 'json', lua = 'lua', markdown = 'markdown', python = 'python',
  vim = 'vim', help = 'vimdoc', query = 'query' }
for ft, lang in pairs(expected) do
  local before = #started
  local buf = buffer(ft)
  assert(#started == before + 1, 'not attached: ' .. ft)
  assert(started[#started].buf == buf and started[#started].lang == lang, ft)
  assert(vim.bo[buf].indentexpr == "v:lua.require'nvim-treesitter'.indentexpr()", ft)
end
local before = #started
local unrelated = buffer('text')
assert(#started == before and vim.bo[unrelated].indentexpr == 'existing_indent()')
""")

    def test_missing_parsers_are_requested_asynchronously_and_indent_is_preserved(self):
        self.run_nvim("""
installed.markdown = nil
installed.markdown_inline = nil
installed.bash = nil
attach()
assert(type(pending) == 'function', 'installation must not wait at startup')
local requested = {}
for _, name in ipairs(requests) do requested[name] = true end
assert(requested.markdown and requested.markdown_inline and requested.bash)
local md = buffer('markdown')
local sh = buffer('sh')
assert(#started == 0)
assert(vim.bo[md].indentexpr == 'existing_indent()')
assert(vim.bo[sh].indentexpr == 'existing_indent()')
""")

    def test_fresh_parser_site_is_on_runtimepath_before_async_install_and_native_lookup_finds_it(self):
        self.run_nvim("""
local site = vim.fn.stdpath('data') .. '/site'
assert(not vim.uv.fs_stat(site), 'fixture must begin without a parser site')
assert(#vim.api.nvim_get_runtime_file('parser/python.so', true) == 0)
installed.python = nil
attach()
assert(type(pending) == 'function', 'must not wait for installation')
assert(vim.tbl_contains(vim.opt.runtimepath:get(), site), 'native parser path missing')
local count = 0
for _, path in ipairs(vim.opt.runtimepath:get()) do if path == site then count = count + 1 end end
assert(count == 1, 'parser site should not duplicate runtimepath entries')
local buf = buffer('python')
assert(#started == 0 and vim.bo[buf].indentexpr == 'existing_indent()')
vim.fn.mkdir(site .. '/parser', 'p')
vim.fn.writefile({'fixture parser'}, site .. '/parser/python.so')
assert(vim.deep_equal(vim.api.nvim_get_runtime_file('parser/python.so', true),
  {site .. '/parser/python.so'}), 'native parser discovery did not see async install')
installed.python = true
pending(nil)
assert(#started == 1 and started[1].buf == buf and started[1].lang == 'python')
""")

    def test_successful_install_rechecks_open_buffers_not_the_current_buffer(self):
        self.run_nvim("""
installed.python = nil
installed.markdown = nil
attach()
local py = buffer('python')
local md = buffer('markdown')
local other = buffer('text')
vim.api.nvim_set_current_buf(other)
assert(#started == 0)
installed.python, installed.markdown = true, true
pending(nil)
assert(#started == 2, vim.inspect(started))
local seen = {}
for _, call in ipairs(started) do seen[call.buf] = call.lang end
assert(seen[py] == 'python' and seen[md] == 'markdown' and not seen[other])
assert(vim.bo[py].indentexpr ~= 'existing_indent()')
assert(vim.bo[md].indentexpr ~= 'existing_indent()')
assert(vim.bo[other].indentexpr == 'existing_indent()')
""")

    def test_failed_install_and_buffer_lifecycle_never_write_unrelated_buffers(self):
        self.run_nvim("""
installed.python = nil
attach()
local deleted = buffer('python')
local changed = buffer('python')
local still_missing = buffer('python')
local other = buffer('text')
vim.api.nvim_buf_delete(deleted, { force = true })
vim.bo[changed].filetype = 'text'
pending('failed installation')
assert(#started == 0)
installed.python = true
vim.api.nvim_set_current_buf(other)
pending(nil)
assert(#started == 1 and started[1].buf == still_missing)
assert(vim.bo[changed].indentexpr == 'existing_indent()')
assert(vim.bo[other].indentexpr == 'existing_indent()')
""")

    def test_failed_native_start_does_not_replace_indent(self):
        self.run_nvim("""
vim.treesitter.start = function() error('compiled parser unusable') end
attach()
local buf = buffer('lua')
assert(vim.bo[buf].indentexpr == 'existing_indent()')
""")

    def test_completion_uses_current_filetype_and_current_parser_availability(self):
        self.run_nvim("""
installed.python = nil
installed.bash = nil
attach()
local changed = buffer('python')
local unavailable = buffer('python')
vim.bo[changed].filetype = 'sh'
installed.bash = true
pending(nil)
assert(#started == 1 and started[1].buf == changed and started[1].lang == 'bash')
assert(vim.bo[unavailable].indentexpr == 'existing_indent()')
""")

    def test_completion_survives_a_buffer_specific_provider_error(self):
        self.run_nvim("""
installed.python = nil
attach()
local first = buffer('python')
local second = buffer('python')
installed.python = true
local get_installed = plugin.get_installed
-- Simulate a provider error on exactly one callback without relying on ordering.
local calls = 0
plugin.get_installed = function(kind)
  calls = calls + 1
  if calls == 1 then error('provider failure') end
  return get_installed(kind)
end
pending(nil)
assert(#started == 1 and (started[1].buf == first or started[1].buf == second))
""")

    def test_start_that_changes_buffer_eligibility_does_not_write_indent(self):
        self.run_nvim("""
vim.treesitter.start = function(buf)
  vim.bo[buf].filetype = 'text'
end
attach()
local buf = buffer('lua')
assert(vim.bo[buf].indentexpr == 'existing_indent()')
""")


if __name__ == "__main__":
    unittest.main()
