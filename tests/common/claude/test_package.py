"""Offline checks for the `claude` stow package.

Run from the repository root:
python3 -m unittest discover -s tests/common/claude -v
No Claude Code, model calls or changes outside a temporary directory.
"""

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "common/claude"
CLAUDE = PACKAGE / ".claude"
OPENCODE = ROOT / "common/opencode/.config/opencode"

BUILTIN_AGENTS = {"Explore", "general-purpose", "Plan"}
TOOLS = {"Agent", "Bash", "Edit", "Write", "NotebookEdit", "Read", "Glob", "Grep",
         "Skill", "WebFetch", "WebSearch", "AskUserQuestion"}
MODELS = {"opus", "sonnet", "haiku", "fable", "inherit"}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
# Skills owned by the owner: never auto-invoked by the model.
OWNER_ONLY = {"implement", "implement-spec", "ship", "recap"}
# Claude Code built-in commands a user skill must not shadow.
BUILTIN_COMMANDS = {"code-review", "simplify", "init", "security-review", "loop",
                    "schedule", "run", "review"}


def frontmatter(path):
    text = path.read_text()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if match is None:
        raise AssertionError(f"{path} has no frontmatter")
    fields, key = {}, None
    for line in match.group(1).splitlines():
        if line.startswith("  - ") and key:
            fields.setdefault(key, []).append(line[4:].strip())
        elif ":" in line:
            key, _, value = line.partition(":")
            value = value.strip()
            fields[key] = json.loads(value) if value.startswith('"') else (value or [])
    return fields


class Package(unittest.TestCase):
    def test_settings_are_strict_json_and_wire_the_hook(self):
        settings = json.loads((CLAUDE / "settings.json").read_text())
        hooks = settings["hooks"]["PreToolUse"]
        commands = [h["command"] for group in hooks for h in group["hooks"]]
        self.assertIn('python3 "$HOME/.claude/hooks/policy.py"', commands)
        self.assertTrue((CLAUDE / "hooks/policy.py").is_file())
        matcher = hooks[0]["matcher"]
        for tool in ("Agent", "Bash", "Read", "Edit", "Write", "NotebookEdit", "mcp__drawio__"):
            self.assertIn(tool, matcher)
        self.assertEqual(hooks[0]["hooks"][0].get("onFailure"), "block")

    def test_settings_never_allow_what_the_workflow_forbids(self):
        allow = json.loads((CLAUDE / "settings.json").read_text())["permissions"]["allow"]
        for rule in allow:
            self.assertNotRegex(rule, r"merge|push|reset|rm |sudo|Edit\(|Write\(")

    def test_agents_are_valid_and_reference_existing_tools_and_skills(self):
        agents = sorted((CLAUDE / "agents").glob("*.md"))
        self.assertEqual(len(agents), 7)
        for path in agents:
            with self.subTest(agent=path.stem):
                fm = frontmatter(path)
                self.assertEqual(fm["name"], path.stem)
                self.assertTrue(fm["description"])
                self.assertIn(fm["model"], MODELS)
                if "effort" in fm:
                    self.assertIn(fm["effort"], EFFORTS)
                for tool in filter(None, re.split(r",\s*", fm.get("disallowedTools", ""))):
                    self.assertIn(tool, TOOLS)
                for skill in fm.get("skills", []):
                    self.assertTrue((CLAUDE / "skills" / skill / "SKILL.md").is_file(), skill)

    def test_delivery_and_interview_roles_cannot_nest_agents(self):
        for name in ("builder", "merger", "tester", "reviewer", "tutor"):
            fm = frontmatter(CLAUDE / "agents" / f"{name}.md")
            self.assertIn("Agent", fm["disallowedTools"], name)
        for name in ("tester", "reviewer", "tutor"):
            fm = frontmatter(CLAUDE / "agents" / f"{name}.md")
            self.assertIn("Edit", fm["disallowedTools"], name)

    def test_hook_role_names_match_agent_files(self):
        sys.dont_write_bytecode = True  # keep __pycache__ out of the stow package
        spec = importlib.util.spec_from_file_location("policy", CLAUDE / "hooks/policy.py")
        policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(policy)
        names = {p.stem for p in (CLAUDE / "agents").glob("*.md")}
        roles = (policy.DELIVERY_ROLES | set(policy.SHELL_ALLOW) | set(policy.GIT_DENY)
                 | set(policy.EDIT_ALLOW) | set(policy.AGENT_ALLOW) | policy.DRAWIO_ROLES
                 | policy.NO_AGENTS | {"orchestrator", "planner"})
        self.assertLessEqual(roles, names)
        for allowed in policy.AGENT_ALLOW.values():
            self.assertLessEqual(allowed, names | BUILTIN_AGENTS)

    def test_skills_resolve_and_names_match_directories(self):
        skills = sorted(p for p in (CLAUDE / "skills").iterdir() if p.is_dir())
        self.assertEqual(len(skills), 15)
        for path in skills:
            with self.subTest(skill=path.name):
                fm = frontmatter(path / "SKILL.md")
                self.assertEqual(fm["name"], path.name)
                self.assertNotIn(path.name, BUILTIN_COMMANDS)
                owner_only = fm.get("disable-model-invocation") == "true"
                self.assertEqual(owner_only, path.name in OWNER_ONLY)

    def test_package_has_no_broken_or_absolute_symlinks(self):
        for path in CLAUDE.rglob("*"):
            if path.is_symlink():
                target = path.readlink()
                self.assertFalse(target.is_absolute(), path)
                self.assertTrue(path.exists(), f"broken link {path} -> {target}")
                self.assertTrue(path.resolve().is_relative_to(OPENCODE), path)

    def test_adapted_copies_are_free_of_opencode_mechanics(self):
        for path in CLAUDE.rglob("*.md"):
            if any(p.is_symlink() for p in [path, *path.parents]) or path.name == "CLAUDE-ADAPTATION.md":
                continue
            text = path.read_text()
            with self.subTest(path=path.relative_to(CLAUDE)):
                for word in ("OpenCode", "opencode", "session_move", "Location", "skill({"):
                    self.assertNotIn(word, text)

    def test_adapted_sources_have_not_drifted(self):
        lock = json.loads((CLAUDE / "workflow/adapted-from.json").read_text())["files"]
        self.assertEqual(len({(e["copy"], e["source"]) for e in lock}), len(lock))
        for entry in lock:
            copy = entry["copy"]
            with self.subTest(copy=copy, source=entry["source"]):
                self.assertTrue((CLAUDE / copy).is_file())
                digest = hashlib.sha256((OPENCODE / entry["source"]).read_bytes()).hexdigest()
                self.assertEqual(digest, entry["sha256"],
                                 f"{entry['source']} changed: port it to {copy}, then update the hash")

    def test_relative_markdown_references_resolve(self):
        pattern = re.compile(r"`(\.\./[^`\s]+\.md)`|\]\((\.\.?/?[^)\s]+\.md)\)")
        for path in list((CLAUDE / "skills").glob("*/*.md")) + list((CLAUDE / "workflow").glob("*.md")):
            if path.parent.is_symlink() or path.is_symlink():
                continue
            for match in pattern.finditer(path.read_text()):
                ref = match.group(1) or match.group(2)
                with self.subTest(path=path.name, ref=ref):
                    self.assertTrue((path.parent / ref).exists())

    def test_home_paths_named_in_prompts_exist_in_the_package(self):
        pattern = re.compile(r"~/\.claude/((?:skills|agents|hooks)/[\w./-]+\.(?:md|py))")
        for path in CLAUDE.rglob("*.md"):
            for ref in pattern.findall(path.read_text()):
                with self.subTest(path=path.name, ref=ref):
                    self.assertTrue((CLAUDE / ref).exists())

    @unittest.skipUnless(shutil.which("stow"), "stow not installed")
    def test_stow_installs_resolvable_links_without_the_readme(self):
        with tempfile.TemporaryDirectory(prefix="claude-stow-") as home:
            (Path(home) / ".claude/skills").mkdir(parents=True)
            subprocess.run(["stow", "-t", home, "-d", str(ROOT / "common"), "claude"],
                           check=True, capture_output=True)
            installed = Path(home) / ".claude"
            self.assertFalse((Path(home) / "README.md").exists())
            for rel in ("settings.json", "hooks/policy.py", "agents/builder.md",
                        "skills/brainstorm/SKILL.md", "skills/ship/SKILL.md",
                        "skills/setup-matt-pocock-skills/domain.md", "workflow/UPSTREAM.md",
                        "mcp/install.sh"):
                self.assertTrue((installed / rel).is_file(), rel)


if __name__ == "__main__":
    unittest.main()
