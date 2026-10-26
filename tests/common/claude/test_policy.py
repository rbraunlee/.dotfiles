"""PreToolUse policy hook checks against throwaway Git repositories.

Run from the repository root:
python3 -m unittest discover -s tests/common/claude -v
No Claude Code, model calls or mutation outside the temporary directory.
"""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HOOK = Path(__file__).resolve().parents[3] / "common/claude/.claude/hooks/policy.py"


def run(*args, cwd):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


class PolicyHook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="claude-policy-")
        root = Path(cls.tmp.name)
        cls.primary = root / "repo"
        cls.primary.mkdir()
        env = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        os.environ.update(env)
        run("git", "init", "-q", "-b", "main", cwd=cls.primary)
        run("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
            "--allow-empty", "-m", "init", cwd=cls.primary)
        cls.worktree = root / "wt"
        run("git", "worktree", "add", "-q", "-b", "feature/x", str(cls.worktree), cwd=cls.primary)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def decide(self, tool, tool_input, cwd=None, role=None):
        event = {"tool_name": tool, "tool_input": tool_input,
                 "cwd": str(cwd or self.primary), "hook_event_name": "PreToolUse"}
        if role:
            event["agent_type"] = role
        out = subprocess.run(["python3", str(HOOK)], input=json.dumps(event),
                             capture_output=True, text=True, check=True)
        if not out.stdout.strip():
            return None
        return json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"]

    def bash(self, command, cwd=None, role=None):
        return self.decide("Bash", {"command": command}, cwd, role)

    # main protection, every session ----------------------------------------
    def test_switching_to_main_is_denied_but_restoring_a_file_is_not(self):
        self.assertEqual(self.bash("git switch main", self.worktree), "deny")
        self.assertEqual(self.bash("git -c x=y checkout main", self.worktree), "deny")
        self.assertIsNone(self.bash("git checkout main -- README.md", self.worktree))

    def test_pushes_to_main_are_denied_in_every_spelling(self):
        for cmd in ("git push origin main", "git push origin +main",
                    "git push origin HEAD:refs/heads/main", "git push --all origin",
                    "FOO=1 git -C . push origin feature:main"):
            self.assertEqual(self.bash(cmd, self.worktree), "deny", cmd)
        self.assertIsNone(self.bash("git push origin feature/x", self.worktree))

    def test_bare_push_is_denied_only_on_main(self):
        self.assertEqual(self.bash("git push"), "deny")
        self.assertIsNone(self.bash("git push", self.worktree))

    def test_force_branch_operations_on_main_are_denied(self):
        for cmd in ("git branch -f main HEAD", "git branch -D main",
                    "git branch --delete --force main"):
            self.assertEqual(self.bash(cmd, self.worktree), "deny", cmd)

    def test_gh_pr_merge_is_denied_even_when_chained(self):
        self.assertEqual(self.bash("echo hi && gh pr merge 3"), "deny")
        self.assertEqual(self.bash("echo $(gh pr merge 3)"), "deny")

    def test_merging_into_main_asks_except_for_the_shipper(self):
        self.assertEqual(self.bash("git merge --no-ff feature/x"), "ask")
        self.assertEqual(self.bash("git merge --no-ff feature/x", role="orchestrator"), "ask")
        self.assertIsNone(self.bash("git merge --no-ff feature/x", role="shipper"))
        self.assertEqual(self.bash("git merge feature/x", role="shipper"), "ask")
        self.assertIsNone(self.bash("git merge --abort"))
        self.assertIsNone(self.bash("git merge --no-ff other", self.worktree))

    # delivery routing ------------------------------------------------------
    def test_delivery_roles_must_cd_into_their_worktree(self):
        self.assertEqual(self.bash("pytest", role="builder"), "deny")
        self.assertIsNone(self.bash(f"cd '{self.worktree}' && pytest", role="builder"))
        self.assertEqual(self.bash(f"cd '{self.worktree}' && cd '{self.primary}' && ls",
                                   role="builder"), "deny")
        self.assertEqual(self.bash(f"git -C '{self.primary}' status",
                                   self.worktree, role="merger"), "deny")

    def test_delivery_roles_edit_only_inside_a_worktree(self):
        primary_file = str(self.primary / "a.py")
        wt_file = str(self.worktree / "a.py")
        self.assertEqual(self.decide("Write", {"file_path": primary_file}, role="builder"), "deny")
        self.assertIsNone(self.decide("Write", {"file_path": wt_file}, role="builder"))
        self.assertIsNone(self.decide("Write", {"file_path": primary_file}))

    def test_role_specific_git_denials(self):
        wt = f"cd '{self.worktree}' && "
        self.assertEqual(self.bash(wt + "git merge t", role="builder"), "deny")
        self.assertEqual(self.bash(wt + "git commit -m x", role="tester"), "deny")
        self.assertIsNone(self.bash(wt + "git commit -m x", role="builder"))

    # read-only and limited roles ------------------------------------------
    def test_reviewer_shell_is_read_only(self):
        wt = f"cd '{self.worktree}' && "
        self.assertIsNone(self.bash(wt + "git diff a b", role="reviewer"))
        self.assertIsNone(self.bash(wt + "git merge-base --is-ancestor a b", role="reviewer"))
        for cmd in ("git diff a b > out.txt", "git diff --output=x a b", "git commit -m x",
                    "find . -name x", "git worktree add y", "git -C . diff"):
            self.assertEqual(self.bash(wt + cmd, role="reviewer"), "deny", cmd)

    def test_interview_roles_only_read_manuals(self):
        self.assertIsNone(self.bash("MANPAGER=cat PAGER=cat man git", role="tutor"))
        self.assertEqual(self.bash("ls", role="aligner"), "deny")

    def test_planner_asks_for_non_read_only_commands(self):
        self.assertIsNone(self.bash("git log --oneline -3", role="planner"))
        self.assertEqual(self.bash("npm install", role="planner"), "ask")

    def test_edit_allowlists_are_relative_to_the_repository(self):
        doc = str(self.primary / "docs/plans/x/approval.md")
        code = str(self.primary / "src/app.py")
        self.assertIsNone(self.decide("Edit", {"file_path": doc}, role="shipper"))
        self.assertEqual(self.decide("Edit", {"file_path": code}, role="shipper"), "deny")
        self.assertIsNone(self.decide("Write", {"file_path": str(self.primary / "CONTEXT.md")},
                                      role="aligner"))
        self.assertEqual(self.decide("Write", {"file_path": str(self.primary / "docsx/a.md")},
                                     role="brainstormer"), "deny")
        self.assertEqual(self.decide("Edit", {"file_path": doc}, role="reviewer"), "deny")

    # secrets and MCP -------------------------------------------------------
    def test_env_example_is_the_only_env_exception(self):
        for name in (".env", ".env.local", "prod.env", "id_ed25519.pub", "auth.json"):
            self.assertEqual(self.decide("Read", {"file_path": str(self.primary / name)}),
                             "deny", name)
        self.assertIsNone(self.decide("Read", {"file_path": str(self.primary / ".env.example")}))
        self.assertIsNone(self.decide("Edit", {"file_path": str(self.primary / ".env.example")}))

    def test_drawio_is_limited_to_interview_roles(self):
        tool = "mcp__drawio__open_drawio_mermaid"
        self.assertEqual(self.decide(tool, {}), "deny")
        self.assertEqual(self.decide(tool, {}, role="planner"), "deny")
        self.assertIsNone(self.decide(tool, {}, role="aligner"))

    def test_line_continuations_and_newlines_do_not_hide_commands(self):
        self.assertEqual(self.bash("echo hi\ngh pr merge 3"), "deny")
        cmd = "GIT_AUTHOR_NAME='Claude Agent' \\\nGIT_COMMITTER_NAME='Claude Agent' \\\ngit merge --no-ff x"
        self.assertEqual(self.bash(cmd), "ask")

    def test_roles_launch_only_their_subagent_types(self):
        launch = lambda kind, role: self.decide("Agent", {"subagent_type": kind}, role=role)
        self.assertIsNone(launch("builder", "orchestrator"))
        self.assertEqual(launch("cleaner", "orchestrator"), "deny")
        self.assertIsNone(launch("Explore", "planner"))
        self.assertEqual(launch("general-purpose", "planner"), "deny")
        self.assertEqual(self.decide("Agent", {}, role="shipper"), "deny")
        self.assertEqual(launch("Explore", "builder"), "deny")
        self.assertIsNone(launch("cleaner", None))

    def test_unparseable_commands_are_denied(self):
        self.assertEqual(self.bash("echo 'unterminated"), "deny")


if __name__ == "__main__":
    unittest.main()
