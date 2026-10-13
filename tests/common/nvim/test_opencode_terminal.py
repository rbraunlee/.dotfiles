"""Exercise the real configured mapping with a fake executable and native terminal job."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


KEYMAPS = Path(__file__).resolve().parents[3] / "common/nvim/.config/nvim/lua/config/keymaps.lua"


class OpenCodeTerminal(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nvim-opencode-test-", dir="/tmp/opencode")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.project = self.root / "project with spaces"
        self.project.mkdir()
        self.other = self.root / "other"
        self.other.mkdir()
        self.source = self.project / "unsaved.lua"
        self.source.write_text("original\n")
        fake = self.bin / "opencode"
        fake.write_text("""#!/usr/bin/python3
import os
import sys
with open(os.environ['FAKE_LAUNCHES'], 'a') as log:
    log.write(os.getcwd() + '\\n')
    log.flush()
for line in sys.stdin:
    if line.strip() == 'quit':
        break
    with open(os.environ['FAKE_INPUT'], 'a') as log:
        log.write(line)
        log.flush()
""")
        fake.chmod(0o755)

    def run_nvim(self, checks):
        script = self.root / "checks.lua"
        script.write_text("""
vim.g.mapleader = ' '
assert(vim.fn.exepath('opencode') == """ + repr(str(self.bin / "opencode")) + """,
  'test must resolve only the fake OpenCode executable')
vim.opt.runtimepath:prepend(""" + repr(str(KEYMAPS.parent.parent.parent)) + """)
dofile(""" + repr(str(KEYMAPS)) + """)
local notices = {}
vim.notify = function(msg, level) table.insert(notices, {msg = msg, level = level}) end
vim.cmd.edit(vim.fn.fnameescape(""" + repr(str(self.source)) + """))
vim.api.nvim_buf_set_lines(0, 0, -1, false, {'unsaved change'})
local source = vim.api.nvim_get_current_buf()
local source_win = vim.api.nvim_get_current_win()
local function toggle()
  local mapping = vim.fn.maparg('<leader>ot', 'n', false, true)
  assert(mapping and type(mapping.callback) == 'function', 'missing configured OpenCode toggle')
  vim.cmd.normal(' ot')
end
local function wait_for(path, lines)
  assert(vim.wait(3000, function()
    local file = io.open(path)
    if not file then return false end
    local value = file:read('*a')
    file:close()
    local count = 0
    for _ in value:gmatch('[^\\n]+') do count = count + 1 end
    return count >= lines
  end, 10), 'fake job did not write ' .. path)
end
""" + checks)
        env = {"PATH": str(self.bin) + os.pathsep + os.defpath,
               "FAKE_LAUNCHES": str(self.root / "launches"), "FAKE_INPUT": str(self.root / "input")}
        self.assertTrue((self.bin / "opencode").is_file())
        for name in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
            location = self.root / name
            location.mkdir(exist_ok=True)
            env[name] = str(location)
        env["NVIM_LOG_FILE"] = str(self.root / "nvim.log")
        result = subprocess.run(
            [shutil.which("nvim"), "--headless", "-u", "NONE", "--noplugin", "-i", "NONE", "-l", str(script)],
            cwd=self.project, env=env, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_toggle_launches_once_and_reopens_live_terminal(self):
        self.run_nvim("""
assert(vim.fn.filereadable(""" + repr(str(self.root / "launches")) + """) == 0,
  'loading keymaps must not start OpenCode')
toggle()
local terminal = vim.api.nvim_get_current_buf()
local job = vim.b[terminal].terminal_job_id
assert(vim.bo[terminal].buftype == 'terminal' and job > 0)
assert(vim.api.nvim_get_current_win() ~= source_win)
assert(vim.api.nvim_win_get_position(0)[2] > vim.api.nvim_win_get_position(source_win)[2])
wait_for(""" + repr(str(self.root / "launches")) + """, 1)
toggle()
assert(vim.api.nvim_get_current_buf() == source and vim.api.nvim_buf_is_loaded(terminal))
assert(vim.fn.jobwait({job}, 0)[1] == -1)
toggle()
assert(vim.api.nvim_get_current_buf() == terminal and vim.b[terminal].terminal_job_id == job)
assert(vim.fn.readfile(""" + repr(str(self.root / "launches")) + """)[1] == """ + repr(str(self.project)) + """)
assert(#vim.fn.readfile(""" + repr(str(self.root / "launches")) + """) == 1)
""")

    def test_double_escape_native_mapping_is_local_and_survives_relaunch(self):
        self.run_nvim("""
local function escape_mapping(buffer)
  for _, map in ipairs(vim.api.nvim_buf_get_keymap(buffer, 't')) do
    if map.lhs == '<Esc><Esc>' then return map end
  end
end
assert(escape_mapping(source) == nil, 'source must not acquire a terminal mapping')
toggle()
local first = vim.api.nvim_get_current_buf()
local job = vim.b[first].terminal_job_id
local map = escape_mapping(first)
assert(map, 'launcher terminal needs buffer-local double Escape')
assert(map.rhs == [[<C-\\><C-N>]] and map.noremap == 1 and map.nowait == 0,
  'double Escape must invoke native terminal-normal mode: ' .. vim.inspect(map))
assert(vim.api.nvim_get_current_buf() == first and vim.fn.jobwait({job}, 0)[1] == -1)
assert(escape_mapping(source) == nil)
toggle()
assert(vim.api.nvim_get_current_buf() == source and vim.api.nvim_buf_is_loaded(first))
toggle()
assert(vim.api.nvim_get_current_buf() == first and vim.b[first].terminal_job_id == job)
assert(escape_mapping(first), 'hide/reopen must retain the mapping')
vim.cmd.stopinsert()
vim.cmd.close()
vim.cmd('botright vsplit')
vim.cmd.enew()
local unrelated = vim.api.nvim_get_current_buf()
vim.fn.termopen({'opencode'})
assert(escape_mapping(unrelated) == nil, 'other terminals must not inherit the mapping')
vim.cmd.stopinsert()
vim.cmd.close()
vim.api.nvim_buf_delete(unrelated, {force = true})
vim.api.nvim_buf_delete(first, {force = true})
toggle()
local second = vim.api.nvim_get_current_buf()
assert(second ~= first and escape_mapping(second), 'relaunch needs its own mapping')
assert(escape_mapping(source) == nil)
""")

    def test_ordinary_window_close_keeps_job_and_source_then_reopens(self):
        self.run_nvim("""
vim.cmd.lcd(vim.fn.fnameescape(""" + repr(str(self.project)) + """))
local original_cwd = vim.fn.getcwd(-1, -1)
toggle()
local terminal = vim.api.nvim_get_current_buf()
local job = vim.b[terminal].terminal_job_id
wait_for(""" + repr(str(self.root / "launches")) + """, 1)
vim.fn.chansend(job, 'synthetic message\\n')
wait_for(""" + repr(str(self.root / "input")) + """, 1)
vim.cmd.close()
assert(vim.api.nvim_get_current_buf() == source and vim.api.nvim_buf_is_loaded(terminal))
assert(vim.bo[source].modified and vim.api.nvim_buf_get_lines(source, 0, 1, false)[1] == 'unsaved change')
assert(vim.fn.getcwd(-1, -1) == original_cwd and vim.fn.getcwd(0, 0) == """ + repr(str(self.project)) + """)
vim.cmd.cd(vim.fn.fnameescape(""" + repr(str(self.other)) + """))
toggle()
assert(vim.api.nvim_get_current_buf() == terminal and vim.b[terminal].terminal_job_id == job)
assert(#vim.fn.readfile(""" + repr(str(self.root / "launches")) + """) == 1)
assert(vim.fn.readfile(""" + repr(str(self.root / "input")) + """)[1] == 'synthetic message')
assert(vim.fn.readfile(""" + repr(str(self.source)) + """)[1] == 'original')
""")

    def test_exited_job_and_deleted_buffer_allow_fresh_launch(self):
        self.run_nvim("""
toggle()
local first = vim.api.nvim_get_current_buf()
local job = vim.b[first].terminal_job_id
wait_for(""" + repr(str(self.root / "launches")) + """, 1)
vim.fn.chansend(job, 'quit\\n')
assert(vim.wait(3000, function() return vim.fn.jobwait({job}, 0)[1] ~= -1 end, 10))
toggle()
local second = vim.api.nvim_get_current_buf()
assert(second ~= first and vim.bo[second].buftype == 'terminal')
assert(#vim.api.nvim_list_wins() == 2, 'relaunch must not leave a dead terminal split behind')
wait_for(""" + repr(str(self.root / "launches")) + """, 2)
vim.cmd.close()
vim.api.nvim_buf_delete(second, {force = true})
toggle()
assert(vim.api.nvim_get_current_buf() ~= second and vim.bo.buftype == 'terminal')
wait_for(""" + repr(str(self.root / "launches")) + """, 3)
""")

    def test_missing_executable_does_not_disturb_source(self):
        self.run_nvim("""
local executable = vim.fn.executable
vim.fn.executable = function(name)
  if name == 'opencode' then return 0 end
  return executable(name)
end
toggle()
assert(vim.api.nvim_get_current_buf() == source and vim.api.nvim_get_current_win() == source_win,
  vim.inspect({vim.api.nvim_get_current_buf(), source, vim.api.nvim_get_current_win(), source_win, notices, vim.env.PATH}))
assert(#vim.api.nvim_list_wins() == 1 and vim.bo[source].modified,
  vim.inspect({vim.api.nvim_list_wins(), vim.bo[source].modified, notices, vim.env.PATH}))
assert(#notices == 1 and notices[1].level == vim.log.levels.ERROR)
assert(notices[1].msg:find('install opencode', 1, true))
""")

    def test_launch_uses_window_cwd_without_mutating_editor_directory(self):
        self.run_nvim("""
vim.cmd.cd(vim.fn.fnameescape(""" + repr(str(self.other)) + """))
vim.cmd.lcd(vim.fn.fnameescape(""" + repr(str(self.project)) + """))
local global = vim.fn.getcwd(-1, -1)
local local_dir = vim.fn.getcwd(0, 0)
toggle()
wait_for(""" + repr(str(self.root / "launches")) + """, 1)
assert(vim.fn.readfile(""" + repr(str(self.root / "launches")) + """)[1] == local_dir)
toggle()
assert(vim.fn.getcwd(-1, -1) == global and vim.fn.getcwd(0, 0) == local_dir)
assert(vim.api.nvim_get_current_buf() == source and vim.bo[source].modified)
""")

    def test_failed_job_start_reports_error_and_keeps_source(self):
        self.run_nvim("""
vim.fn.termopen = function() error('synthetic spawn failure') end
toggle()
assert(vim.api.nvim_get_current_buf() == source and vim.api.nvim_get_current_win() == source_win)
assert(#vim.api.nvim_list_wins() == 1 and vim.bo[source].modified)
assert(#notices == 1 and notices[1].level == vim.log.levels.ERROR)
assert(notices[1].msg:find('launch failed', 1, true))
""")


if __name__ == "__main__":
    unittest.main()
