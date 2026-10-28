"""Exercise the configured search mappings without loading Telescope or user init."""

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / "common/nvim/.config/nvim/lua/plugins/telescope.lua"
PINNED_PROVIDER = Path(__file__).parent / "fixtures/pinned_telescope_find_files.lua"


class ConfigurationSearch(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nvim-search-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "relocated dotfiles"
        self.source = self.repo / "common/nvim/.config/nvim"
        self.repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True,
                       env={"PATH": os.defpath, "HOME": str(self.root), "GIT_CONFIG_NOSYSTEM": "1",
                            "GIT_CONFIG_GLOBAL": os.devnull})
        for group in ("common", "linux", "macos"):
            (self.repo / group).mkdir(exist_ok=True)
        (self.source / "lua/config").mkdir(parents=True)
        (self.source / "init.lua").write_text("-- fixture\n")
        (self.source / "lua/config/keymaps.lua").write_text("-- fixture\n")
        (self.repo / "linux/waybar/.config/waybar").mkdir(parents=True)
        (self.repo / "linux/waybar/.config/waybar/config.jsonc").write_text("{}\n")
        (self.repo / "macos/zsh/.config/zsh").mkdir(parents=True)
        (self.repo / "macos/zsh/.config/zsh/.zshrc").write_text("# fixture\n")
        (self.repo / "README.md").write_text("not an environment package\n")
        (self.source / "lua/config/.env").write_text("ignored from repository root\n")
        (self.repo / ".gitignore").write_text(
            "/common/nvim/.config/nvim/lua/config/.env\n"
            "/common/nvim/.config/nvim/lua/config/*.token\n"
            "!/common/nvim/.config/nvim/lua/config/public.token\n"
        )
        (self.source / "lua/config/restricted.token").write_text("ignored\n")
        (self.source / "lua/config/public.token").write_text("allowed by negation\n")
        (self.source / "lua/.gitignore").write_text("config/nested-secret\n")
        (self.source / "lua/config/nested-secret").write_text("ignored by nested gitignore\n")
        self.config_home = self.root / "XDG_CONFIG_HOME"
        self.config_home.mkdir()
        self.config = self.config_home / "search-test"

    def run_nvim(self, checks, pinned_provider=False):
        script = self.root / "checks.lua"
        builtin_stub = """
package.preload['telescope.builtin'] = function()
  return setmetatable({find_files = function(opts) table.insert(calls, opts) end},
    {__index = function() return function() end end})
end
"""
        if pinned_provider:
            builtin_stub = """
utils = {path_expand = function(path) return path end}
log = {warn = function() end}
make_entry = {gen_from_file = function() return function(path) return {value = path} end end}
finders = {new_oneshot_job = function(command)
  table.insert(jobs, command)
  return command
end}
conf = {file_previewer = function() return {} end, file_sorter = function() return {} end}
pickers = {new = function(options, opts)
  return {find = function()
    table.insert(calls, {options = options, opts = opts, command = jobs[#jobs]})
  end}
end}
package.preload['telescope.builtin'] = function()
  return setmetatable({find_files = dofile(""" + repr(str(PINNED_PROVIDER)) + """)},
    {__index = function() return function() end end})
end
"""
        script.write_text(
            """
vim.g.mapleader = ' '
local calls, notices, jobs = {}, {}, {}
vim.notify = function(msg, level) table.insert(notices, {msg = msg, level = level}) end
package.preload['telescope'] = function()
  return {setup = function() end, load_extension = function() end}
end
package.preload['telescope.themes'] = function()
  return {get_dropdown = function() return {} end}
end
""" + builtin_stub + """
package.preload['telescope.make_entry'] = function()
  return {gen_from_file = function() return function(path) return {value = path} end end}
end
local spec = dofile("""
            + repr(str(PLUGIN))
            + """ )
spec.config()
local function invoke(lhs)
  local expanded = lhs:gsub('<leader>', vim.g.mapleader)
  for _, mapping in ipairs(vim.api.nvim_get_keymap('n')) do
    if mapping.lhs == expanded then
      assert(type(mapping.callback) == 'function', lhs)
      mapping.callback()
      return
    end
  end
  error('mapping missing: ' .. lhs)
end
"""
            + checks
        )
        env = {"PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        for name in ("HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR"):
            location = self.root / name
            location.mkdir()
            env[name] = str(location)
        env["XDG_CONFIG_HOME"] = str(self.config_home)
        env["NVIM_APPNAME"] = "search-test"
        env["NVIM_LOG_FILE"] = str(self.root / "nvim.log")
        result = subprocess.run(
            ["nvim", "--headless", "-u", "NONE", "--noplugin", "-i", "NONE", "-l", str(script)],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_folded_config_searches_active_link_and_only_environment_packages(self):
        self.config.symlink_to(self.source, target_is_directory=True)
        self.run_nvim("""
invoke('<leader>sn')
assert(#calls == 1 and calls[1].cwd == vim.fn.stdpath('config'), vim.inspect(calls))
assert(calls[1].follow and calls[1].hidden and not calls[1].no_ignore)
invoke('<leader>sc')
assert(#calls == 2, vim.inspect(calls))
assert(calls[2].cwd == """ + repr(str(self.repo)) + """, vim.inspect(calls[2]))
assert(calls[2].hidden and not calls[2].no_ignore and not calls[2].follow)
local expected = {""" + ", ".join(repr(str(self.repo / group)) for group in ("common", "linux", "macos")) + """}
assert(vim.deep_equal(calls[2].search_dirs, expected), vim.inspect(calls[2].search_dirs))
assert(#notices == 0)
""")

    def test_individual_file_links_resolve_checkout_without_using_cwd(self):
        self.config.mkdir()
        (self.config / "init.lua").symlink_to(self.source / "init.lua")
        (self.config / "lua").mkdir()
        (self.config / "lua/config").mkdir()
        (self.config / "lua/config/keymaps.lua").symlink_to(self.source / "lua/config/keymaps.lua")
        (self.config / "lua/config/.env").symlink_to(self.source / "lua/config/.env")
        self.run_nvim("""
invoke('<leader>sn')
invoke('<leader>sc')
assert(#calls == 2, vim.inspect(calls))
assert(calls[1].cwd == vim.fn.stdpath('config') and calls[1].follow)
local candidates = vim.fn.systemlist({'rg', '--files', '--hidden', '-L', vim.fn.stdpath('config')})
assert(vim.v.shell_error == 0, vim.inspect(candidates))
local found_keymaps, found_env = false, false
for _, candidate in ipairs(candidates) do
  if candidate:find('keymaps.lua', 1, true) then
    found_keymaps = calls[1].entry_maker(candidate) ~= nil
  elseif candidate:find('lua/config/.env', 1, true) then
    found_env = true
    assert(calls[1].entry_maker(candidate) == nil,
      'individual links must inherit repository-root ignores')
  end
end
assert(found_keymaps and found_env, vim.inspect(candidates))
assert(calls[2].cwd == """ + repr(str(self.repo)) + """)
assert(#calls[2].search_dirs == 3)
""")

    def test_linked_lua_subtree_with_local_init_inherits_repository_ignore_rules(self):
        self.config.mkdir()
        (self.config / "init.lua").write_text("-- local config\n")
        (self.config / "lua").symlink_to(self.source / "lua", target_is_directory=True)
        self.run_nvim("""
invoke('<leader>sn')
assert(#calls == 1 and calls[1].cwd == vim.fn.stdpath('config') and calls[1].follow)
assert(calls[1].entry_maker('lua/config/keymaps.lua'))
assert(calls[1].entry_maker('lua/config/.env') == nil)
invoke('<leader>sc')
assert(#calls == 2 and calls[2].cwd == """ + repr(str(self.repo)) + """)
assert(#notices == 0)
""")

    def test_picker_scopes_reach_linked_files_but_respect_ignores_and_package_boundary(self):
        self.config.mkdir()
        (self.config / "init.lua").symlink_to(self.source / "init.lua")
        (self.config / "lua").symlink_to(self.source / "lua", target_is_directory=True)
        (self.config / ".ignore").write_text("local-secret\n")
        (self.config / "local-secret").write_text("ignored locally\n")
        (self.config / "local-note").write_text("only active config has this\n")
        self.run_nvim("""
local function listed(opts)
  local command = { 'rg', '--files' }
  if opts.hidden then table.insert(command, '--hidden') end
  if opts.follow then table.insert(command, '-L') end
  if opts.no_ignore then table.insert(command, '--no-ignore') end
  for _, path in ipairs(opts.search_dirs or {}) do table.insert(command, path) end
  local previous = vim.fn.getcwd()
  vim.cmd.cd(vim.fn.fnameescape(opts.cwd))
  local files = vim.fn.systemlist(command)
  local code = vim.v.shell_error
  vim.cmd.cd(vim.fn.fnameescape(previous))
  assert(code == 0, vim.inspect(files))
  local visible = {}
  for _, file in ipairs(files) do
    if not opts.entry_maker or opts.entry_maker(file) then table.insert(visible, file) end
  end
  return table.concat(visible, '\\n')
end
invoke('<leader>sn')
assert(vim.fn.executable('git') == 1 and vim.fn.executable('rg') == 1)
assert(vim.fn.system({'git', '-C', """ + repr(str(self.repo)) + """, 'check-ignore', '--no-index', '--quiet', '--',
  """ + repr(str(self.source / 'lua/config/.env')) + """}) == '')
assert(vim.v.shell_error == 0, 'fixture repository-only rule must ignore reachable file')
local active = listed(calls[1])
assert(active:find('init.lua', 1, true) and active:find('lua/config/keymaps.lua', 1, true), active)
assert(active:find('local-note', 1, true), active)
assert(active:find('lua/config/public.token', 1, true), active)
assert(not active:find('lua/config/.env', 1, true), active)
assert(not active:find('restricted.token', 1, true), active)
assert(not active:find('nested-secret', 1, true), active)
assert(not active:find('local-secret', 1, true), active)
invoke('<leader>sc')
local packages = listed(calls[2])
assert(packages:find('waybar/config.jsonc', 1, true), packages)
assert(packages:find('zsh/.config/zsh/.zshrc', 1, true), packages)
assert(packages:find('nvim/.config/nvim/init.lua', 1, true), packages)
assert(not packages:find('lua/config/.env', 1, true), packages)
assert(not packages:find('nested-secret', 1, true), packages)
assert(not packages:find('README.md', 1, true), packages)
assert(not packages:find('/.git/', 1, true), packages)
""")

    def test_missing_repo_reports_useful_error_without_searching_home(self):
        self.config.mkdir()
        (self.config / "init.lua").write_text("-- unrelated standalone config\n")
        self.run_nvim("""
invoke('<leader>sn')
invoke('<leader>sc')
assert(#calls == 1 and calls[1].cwd == vim.fn.stdpath('config'))
assert(#notices == 1 and notices[1].level == vim.log.levels.WARN, vim.inspect(notices))
assert(notices[1].msg:find('dotfiles repository') and notices[1].msg:find('config'), vim.inspect(notices))
""")

    def test_missing_ignore_aware_provider_does_not_open_configuration_picker(self):
        self.config.symlink_to(self.source, target_is_directory=True)
        self.run_nvim("""
local executable = vim.fn.executable
vim.fn.executable = function(name)
  if name == 'rg' or name == 'fd' or name == 'fdfind' then return 0 end
  return executable(name)
end
invoke('<leader>sc')
assert(#calls == 0, 'unsafe fallback could enumerate ignored files: ' .. vim.inspect(calls))
assert(#notices == 1 and notices[1].level == vim.log.levels.WARN, vim.inspect(notices))
assert(notices[1].msg:find('rg', 1, true) and notices[1].msg:find('fd', 1, true), vim.inspect(notices))
""")

    def test_missing_provider_does_not_enumerate_active_config_links(self):
        self.config.symlink_to(self.source, target_is_directory=True)
        self.run_nvim("""
vim.fn.executable = function(name)
  if name == 'rg' or name == 'fd' or name == 'fdfind' then return 0 end
  if name == 'find' then return 1 end
  return 0
end
invoke('<leader>sn')
assert(#calls == 0, 'active config must not fall back to find: ' .. vim.inspect(calls))
assert(#notices == 1 and notices[1].level == vim.log.levels.WARN)
""")

    def pinned_provider_case(self, available, expected):
        self.config.symlink_to(self.source, target_is_directory=True)
        self.run_nvim("""
local executable = vim.fn.executable
local available = {""" + ", ".join("[" + repr(tool) + "] = true" for tool in available) + """}
vim.fn.executable = function(name)
  if name == 'rg' or name == 'fd' or name == 'fdfind' then
    return available[name] and 1 or 0
  end
  if name == 'find' then return 1 end -- pinned fallback must never run
  return executable(name)
end
invoke('<leader>sc')
local expected = """ + repr(expected) + """
if expected == '' then
  assert(#calls == 0 and #jobs == 0, 'must not enumerate or preview: ' .. vim.inspect(calls))
  assert(#notices == 1 and notices[1].level == vim.log.levels.WARN, vim.inspect(notices))
  assert(notices[1].msg:find('rg', 1, true) and notices[1].msg:find('fd', 1, true))
else
  assert(#calls == 1 and #jobs == 1 and #notices == 0, vim.inspect({calls, jobs, notices}))
  local picked = calls[1]
  assert(picked.command[1] == expected, vim.inspect(picked.command))
  assert(picked.command[1] ~= 'find' and picked.command[1] ~= 'where')
  local prefix = expected == 'rg' and {'rg', '--files', '--color', 'never'}
    or {expected, '--type', 'f', '--color', 'never'}
  for i, arg in ipairs(prefix) do assert(picked.command[i] == arg, vim.inspect(picked.command)) end
  if expected ~= 'rg' then assert(picked.command[7] == '.', vim.inspect(picked.command)) end
  assert(vim.tbl_contains(picked.command, '--hidden'), vim.inspect(picked.command))
  assert(not vim.tbl_contains(picked.command, '--no-ignore'), vim.inspect(picked.command))
  assert(not vim.tbl_contains(picked.command, '--no-ignore-parent'))
  assert(not vim.tbl_contains(picked.command, '-L'))
  assert(picked.options.cwd == """ + repr(str(self.repo)) + """)
  assert(picked.options.hidden and not picked.options.no_ignore and not picked.options.follow)
  assert(picked.opts.previewer and picked.opts.sorter, 'default previews and sorters remain available')
  assert(picked.opts.finder == picked.command)
  assert(picked.opts.prompt_title == 'Find Files')
  assert(#picked.command >= 7 and picked.command[#picked.command - 2] == """ + repr(str(self.repo / "common")) + """)
  assert(picked.command[#picked.command - 1] == """ + repr(str(self.repo / "linux")) + """)
  assert(picked.command[#picked.command] == """ + repr(str(self.repo / "macos")) + """)
end
""", pinned_provider=True)

    def test_pinned_rg_provider_selection(self):
        self.pinned_provider_case(("rg", "fd", "fdfind"), "rg")

    def test_pinned_fd_provider_selection(self):
        self.pinned_provider_case(("fd", "fdfind"), "fd")

    def test_pinned_fdfind_provider_selection(self):
        self.pinned_provider_case(("fdfind",), "fdfind")

    def test_pinned_missing_provider_refuses_unix_find(self):
        self.pinned_provider_case((), "")

    def test_pinned_provider_disappearing_after_check_never_selects_find(self):
        self.config.symlink_to(self.source, target_is_directory=True)
        self.run_nvim("""
local count = 0
vim.fn.executable = function(name)
  if name == 'rg' then
    count = count + 1
    return count == 1 and 1 or 0
  end
  if name == 'find' then return 1 end
  return 0
end
invoke('<leader>sc')
assert(#calls == 0 or (#calls == 1 and calls[1].command[1] == 'rg'), vim.inspect(calls))
assert(#jobs == 0 or jobs[1][1] == 'rg', vim.inspect(jobs))
""", pinned_provider=True)

    def test_pinned_active_config_preserves_follow_and_repository_ignore_filter(self):
        self.config.mkdir()
        (self.config / "init.lua").symlink_to(self.source / "init.lua")
        (self.config / "lua").symlink_to(self.source / "lua", target_is_directory=True)
        self.run_nvim("""
invoke('<leader>sn')
assert(#calls == 1 and calls[1].command[1] == 'rg', vim.inspect(calls))
assert(vim.tbl_contains(calls[1].command, '--hidden'))
assert(vim.tbl_contains(calls[1].command, '-L'))
assert(not vim.tbl_contains(calls[1].command, '--no-ignore'))
assert(calls[1].opts.previewer and calls[1].opts.sorter)
assert(calls[1].opts.finder == calls[1].command)
assert(#jobs == 1 and #notices == 0)
assert(calls[1].options.cwd == vim.fn.stdpath('config'))
assert(calls[1].options.entry_maker('lua/config/keymaps.lua'))
assert(calls[1].options.entry_maker('lua/config/.env') == nil,
  'repository-ignored linked file must not be previewed')
""", pinned_provider=True)

    def test_pinned_provider_fixture_matches_locked_selection_contract(self):
        text = PINNED_PROVIDER.read_text()
        implementation = text[text.index("files.find_files = function(opts)"):
                              text.index("\nreturn files.find_files")].rstrip()
        self.assertEqual(hashlib.sha256(implementation.encode()).hexdigest(),
                         "69ee6839ce169bafffca559a099ae49b07ab0a51639b50cb0f8f30ad50755ce2")


if __name__ == "__main__":
    unittest.main()
