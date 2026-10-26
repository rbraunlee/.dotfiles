"""Offline packaging checks; no model calls, credentials or live-home mutations."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[3]
COMMON = ROOT / "common"
CONFIG = COMMON / "codex/.codex"
SKILLS = COMMON / "agent-skills/.agents/skills"


def run(*args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, check=True,
                          timeout=30, **kwargs)


class PackageIntegrity(unittest.TestCase):
    def test_config_and_roles_parse(self):
        config = tomllib.loads((CONFIG / "config.toml").read_text())
        self.assertEqual(config["sandbox_mode"], "workspace-write")
        self.assertEqual(config["approval_policy"], "on-request")
        self.assertNotIn("mcp_servers", config)
        names = set()
        for path in (CONFIG / "agents").glob("*.toml"):
            agent = tomllib.loads(path.read_text())
            self.assertTrue(agent["description"])
            self.assertTrue(agent["developer_instructions"])
            self.assertNotIn("sandbox_mode", agent)
            names.add(agent["name"])
        self.assertEqual(names, {"builder", "tester", "reviewer"})

    def test_optional_integrations_use_environment(self):
        config = tomllib.loads((CONFIG / "integrations.config.toml").read_text())
        servers = config["mcp_servers"]
        self.assertEqual(servers["obsidian"]["bearer_token_env_var"], "OBS_MCP_TOKEN")
        self.assertIn("BRAVE_SEARCH_TOKEN", servers["brave-search"]["env_vars"])
        for server in servers.values():
            self.assertNotIn("http_headers", server)
        dependencies = json.loads(
            (COMMON / "codex/.local/share/codex-mcp/package.json").read_text()
        )["dependencies"]
        for version in dependencies.values():
            self.assertRegex(version, r"^\d+\.\d+\.\d+$")

    def test_skill_names_and_references(self):
        names = set()
        for path in SKILLS.glob("*/SKILL.md"):
            text = path.read_text()
            frontmatter = text.split("---", 2)[1]
            name = re.search(r"(?m)^name: (.+)$", frontmatter).group(1)
            self.assertEqual(name, path.parent.name)
            self.assertNotIn(name, names)
            names.add(name)
            self.assertRegex(frontmatter, r"(?m)^description: .+")
        self.assertGreaterEqual(len(names), 14)
        for path in SKILLS.rglob("*.md"):
            # Templates contain illustrative project links inside fenced blocks.
            prose = re.sub(r"(?ms)^```[^\n]*\n.*?^```\s*$", "", path.read_text())
            for target in re.findall(r"\]\(([^\s)]+)\)", prose):
                if "://" in target or target.startswith(("#", "/")):
                    continue
                target = target.split("#", 1)[0]
                with self.subTest(file=str(path.relative_to(SKILLS)), target=target):
                    self.assertTrue((path.parent / target).exists())


@unittest.skipUnless(shutil.which("stow"), "GNU Stow is not installed")
class StowLifecycle(unittest.TestCase):
    def test_install_restow_unstow_preserves_runtime_state(self):
        with tempfile.TemporaryDirectory(prefix="codex-stow-") as directory:
            base = Path(directory)
            packages = base / "packages"
            home = base / "home"
            home.mkdir()
            for name in ("codex", "agent-skills"):
                shutil.copytree(COMMON / name, packages / name)
            # Match an existing Codex installation, including a private config file.
            (home / ".codex").mkdir()
            runtime = home / ".codex/runtime-sentinel"
            runtime.write_text("preserve runtime state")
            command = ("stow", "--no-folding", "-t", str(home), "-d", str(packages))
            run(*command, "-n", "codex", "agent-skills")
            run(*command, "codex", "agent-skills")
            self.assertTrue((home / ".codex/config.toml").is_symlink())
            self.assertFalse((home / ".agents/skills").is_symlink())
            self.assertFalse((home / ".local/share/codex-mcp").is_symlink())
            self.assertFalse((home / "README.md").exists())
            skill = home / ".agents/skills/implement-spec/SKILL.md"
            self.assertEqual(skill.read_text(), (SKILLS / "implement-spec/SKILL.md").read_text())
            generated = home / ".local/share/codex-mcp/node_modules/sentinel"
            generated.parent.mkdir()
            generated.write_text("installed locally")
            run(*command, "-R", "codex", "agent-skills")
            self.assertEqual(runtime.read_text(), "preserve runtime state")
            run(*command, "-D", "codex", "agent-skills")
            self.assertFalse((home / ".codex/config.toml").exists())
            self.assertEqual(runtime.read_text(), "preserve runtime state")
            self.assertEqual(generated.read_text(), "installed locally")

    def test_existing_configuration_conflicts_without_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="codex-conflict-") as directory:
            home = Path(directory)
            (home / ".codex").mkdir()
            existing = home / ".codex/config.toml"
            existing.write_text("# user's existing config\n")
            result = subprocess.run(
                ["stow", "-n", "--no-folding", "-t", str(home), "-d", str(COMMON), "codex"],
                text=True, capture_output=True, timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(existing.read_text(), "# user's existing config\n")


@unittest.skipUnless(shutil.which("codex"), "Codex CLI is not installed")
class CodexStartup(unittest.TestCase):
    def test_strict_config_without_starting_server(self):
        with tempfile.TemporaryDirectory(prefix="codex-startup-") as directory:
            base = Path(directory)
            config_home = base / ".codex"
            shutil.copytree(CONFIG, config_home)
            env = dict(os.environ, CODEX_HOME=str(config_home))
            for integrations in (False, True):
                with self.subTest(integrations=integrations):
                    # Validate the optional profile as a merged config without
                    # starting servers or inheriting the user's credentials.
                    if integrations:
                        with (config_home / "config.toml").open("a") as output:
                            output.write("\n" + (config_home / "integrations.config.toml").read_text())
                    result = run("codex", "app-server", "--strict-config",
                                 "--print-startup-config", env=env, cwd=base)
                    self.assertIn("appServerVersion", json.loads(result.stdout))


if __name__ == "__main__":
    unittest.main()
