"""Offline assets plus installed OpenCode V2 discovery/permission regression checks.

Run from the repository root:
python3 -m unittest discover -s common/opencode/.config/opencode/tests -v
Runtime tests require OpenCode and this repository's opencode package to be stowed.
No model calls, project mutations or third-party Python dependencies.
"""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest


CONFIG = Path(__file__).resolve().parents[1]
ROOT = CONFIG.parents[3]
SKILLS = CONFIG / "skills"
REQUIRED = {
    "setup-matt-pocock-skills", "grill-with-docs", "grilling", "domain-modeling",
    "to-spec", "to-tickets", "implement", "implement-spec", "tdd", "code-review",
    "codebase-design",
}
ADAPTED = {
    f"{name}/SKILL.md" for name in REQUIRED - {"codebase-design"}
} | {"setup-matt-pocock-skills/issue-tracker-local.md"}


def frontmatter(path):
    text = path.read_text()
    return text.split("---", 2)[1]


def matches(pattern, value):
    # V2 whole-value wildcards, not shell fnmatch's [] character classes.
    regex = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
    if re.fullmatch(regex, value):
        return True
    # The no-arguments form still uses whole-value wildcard matching.
    if pattern.endswith(" *"):
        base = re.escape(pattern[:-2]).replace(r"\*", ".*").replace(r"\?", ".")
        return re.fullmatch(base, value) is not None
    return False


def effect(agent, action, resource):
    result = "ask"
    for rule in agent["permissions"]:
        if matches(rule["action"], action) and matches(rule["resource"], resource):
            result = rule["effect"]
    return result


class AssetTests(unittest.TestCase):
    def test_skill_entries_and_native_agent_frontmatter(self):
        for name in REQUIRED:
            entry = SKILLS / name / "SKILL.md"
            self.assertTrue(entry.is_file(), name)
            self.assertIn(f"name: {name}", frontmatter(entry))
            self.assertIn("description:", frontmatter(entry))
        for path in (CONFIG / "agents").glob("*.md"):
            self.assertNotRegex(
                frontmatter(path),
                r"(?m)^(permission|reasoningEffort|variant|tools|temperature):",
                str(path),
            )

    def test_snapshot_and_unchanged_supporting_files(self):
        lock = json.loads((SKILLS / "upstream-lock.json").read_text())
        self.assertEqual(lock["commit"], "b0618bc436ad893b3c5e84e55fba86586d34a404")
        installed = set()
        for record in lock["files"]:
            path = SKILLS / record["installed"]
            self.assertTrue(path.is_file(), str(path))
            self.assertNotIn(record["installed"], installed)
            installed.add(record["installed"])
            self.assertRegex(record["sha256"], r"^[0-9a-f]{64}$")
            if record["installed"] not in ADAPTED:
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                                 record["sha256"], str(path))
        self.assertIn("Copyright (c) 2026 Matt Pocock",
                      (SKILLS / "MATT-POCOCK-LICENSE.txt").read_text())
        self.assertTrue((CONFIG / "workflow/UPSTREAM.md").is_file())

    def test_supporting_links_resolve(self):
        for name in REQUIRED:
            for path in (SKILLS / name).glob("*.md"):
                # Templates contain illustrative project links, not shipped assets.
                prose = re.sub(r"```.*?```", "", path.read_text(), flags=re.S)
                for target in re.findall(r"\]\(([^)]+)\)", prose):
                    if "://" in target or target.startswith(("#", "/")):
                        continue
                    self.assertTrue((path.parent / target.split("#")[0]).is_file(),
                                    f"{path}: {target}")

    def test_commands_keep_one_primary_context(self):
        for name in ("setup-matt-pocock-skills", "grill-with-docs", "to-spec",
                     "to-tickets", "implement", "implement-spec"):
            path = CONFIG / "commands" / f"{name}.md"
            text = path.read_text()
            self.assertIn("subagent: false", frontmatter(path))
            self.assertIn("$ARGUMENTS", text)
            self.assertNotIn("!`", text)  # No permission-bypassing shell expansion.
            expected = "orchestrator" if name.startswith("implement") else "planner"
            self.assertIn(f"agent: {expected}", frontmatter(path))

    def test_obsolete_runtime_authority_removed(self):
        for path in (CONFIG / "agents").glob("*.md"):
            self.assertNotIn("current-slice.toml", path.read_text(), str(path))
        text = (SKILLS / "implement-spec/SKILL.md").read_text()
        self.assertNotIn("resets onto it", text)
        self.assertIn("integrated and checked", text)

    def test_worker_lifecycle_contract(self):
        graph = " ".join((SKILLS / "implement-spec/SKILL.md").read_text().split())
        contract = " ".join((SKILLS / "implement-spec/LOCAL-EXECUTION.md").read_text().split())
        self.assertIn("only after the assigned child has finished and reported its result", graph)
        self.assertIn("whose sessions have finished", graph)
        self.assertIn("non-force `git worktree remove <exact-path>`", graph)
        self.assertIn("For a noninteractive `opencode run` invocation, use foreground children", contract)
        self.assertIn("not a QA-ready handoff", contract)
        self.assertIn("retrieve the assigned child's original tool records", contract)

    def test_shell_no_argument_matching_retains_wildcards(self):
        self.assertTrue(matches("git push * main *", "git push origin main"))
        self.assertTrue(matches("git push * main *", "git push origin main --force"))
        self.assertFalse(matches("git push * main *", "git push origin feature/domain-model"))


@unittest.skipUnless(shutil.which("opencode"), "OpenCode V2 required for discovery")
class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(["opencode", "debug", "agents"], cwd=ROOT,
                                capture_output=True, text=True, check=True)
        cls.agents = {agent["id"]: agent for agent in json.loads(result.stdout)}

    def test_installed_role_discovery(self):
        for name in ("orchestrator", "planner", "builder", "merger", "tester", "reviewer"):
            self.assertIn(name, self.agents)
            expected = "primary" if name in ("orchestrator", "planner") else "subagent"
            self.assertEqual(self.agents[name]["mode"], expected)
            body = (CONFIG / "agents" / f"{name}.md").read_text().split("---", 2)[2].strip()
            self.assertEqual(self.agents[name]["system"].strip(), body,
                             "Stow this repository's opencode package before runtime tests")

    def test_routine_delivery_needs_no_shell_approval(self):
        for name in ("orchestrator", "builder", "merger", "tester"):
            for command in ("pwd", "git rev-parse HEAD", "python3 -m unittest",
                            "npm test", "npm run lint", "npm run build"):
                self.assertEqual(effect(self.agents[name], "shell", command), "allow",
                                 f"{name}: {command}")
        for name in ("orchestrator", "builder", "merger"):
            for command in ("git add src/example.py", "git commit -m 'fix: example'"):
                self.assertEqual(effect(self.agents[name], "shell", command), "allow")
        self.assertEqual(effect(self.agents["merger"], "shell", "git merge ticket/example"),
                         "allow")
        self.assertEqual(effect(self.agents["builder"], "shell", "git merge ticket/example"),
                         "deny")

    def test_coordinator_is_flat_and_review_is_read_only(self):
        coordinator = self.agents["orchestrator"]
        for name in ("builder", "merger", "tester", "reviewer", "explore"):
            self.assertEqual(effect(coordinator, "subagent", name), "allow")
        self.assertEqual(effect(coordinator, "subagent", "orchestrator"), "deny")
        for name in ("builder", "merger", "tester", "reviewer"):
            self.assertEqual(effect(self.agents[name], "subagent", "general"), "deny")
        for name in ("tester", "reviewer"):
            self.assertEqual(effect(self.agents[name], "edit", "src/example.py"), "deny")
        reviewer = self.agents["reviewer"]
        for command in ("pwd", "git diff base final", "git show HEAD", "git status --short",
                        "git ls-files", "git ls-files --stage"):
            self.assertEqual(effect(reviewer, "shell", command), "allow")
        for command in ("npm test", "git add example", "git commit -m fix",
                        "git diff --output=example", "git log --output=example"):
            self.assertEqual(effect(reviewer, "shell", command), "deny")

    def test_manual_reads_are_allowed_across_roles(self):
        for name in (path.stem for path in (CONFIG / "agents").glob("*.md")):
            for command in ("man ghostty", "man 5 ghostty", "man tmux",
                            "MANPAGER=cat PAGER=cat man ghostty",
                            "MANPAGER=cat PAGER=cat man 5 ghostty"):
                self.assertEqual(effect(self.agents[name], "shell", command), "allow",
                                 f"{name}: {command}")
        for command in ("sh -c 'man ghostty'", "MANPAGER=sh PAGER=sh man ghostty"):
            self.assertEqual(effect(self.agents["reviewer"], "shell", command), "deny")

    def test_protected_actions_and_paths(self):
        for name in ("orchestrator", "builder", "merger", "tester", "reviewer", "planner"):
            agent = self.agents[name]
            self.assertNotEqual(effect(agent, "external_directory", "/etc/*"), "allow")
            self.assertEqual(effect(agent, "read", "config.env"), "deny")
            self.assertEqual(effect(agent, "read", "config.env.example"), "allow")
            self.assertEqual(effect(agent, "edit", "docs/config.env"), "deny", name)
            for command in ("git reset --hard HEAD", "git clean -fd", "git push origin feature/x",
                            "git worktree remove --force /tmp/opencode/x", "rm -rf /home/example"):
                self.assertNotEqual(effect(agent, "shell", command), "allow", f"{name}: {command}")
            for command in ("git switch main", "git checkout main", "git push origin main",
                            "git push origin main --force", "git push origin HEAD:main",
                            "git push origin HEAD:refs/heads/main", "gh pr merge 123"):
                self.assertEqual(effect(agent, "shell", command), "deny", f"{name}: {command}")

    def test_feature_publication_does_not_match_main_substrings(self):
        for command in ("git push origin feature/domain-model", "git push origin feature/main-menu"):
            self.assertEqual(effect(self.agents["orchestrator"], "shell", command), "ask")

    def test_managed_skill_context_remains_readable(self):
        boundary = str(Path.home() / ".config/opencode/skills/implement-spec/*")
        for name in ("orchestrator", "builder", "tester", "reviewer", "planner"):
            self.assertEqual(effect(self.agents[name], "external_directory", boundary),
                             "allow", name)
        for name in ("planner", "aligner", "brainstomer"):
            for path in ("docs/.env", "docs/service.pem", "docs/auth.json"):
                self.assertEqual(effect(self.agents[name], "edit", path), "deny", name)


if __name__ == "__main__":
    unittest.main()
