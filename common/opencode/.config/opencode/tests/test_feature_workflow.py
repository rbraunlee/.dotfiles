"""Offline assets plus fixture-isolated OpenCode V2 rule-model checks.

Run from the repository root:
python3 -m unittest discover -s common/opencode/.config/opencode/tests -v
Runtime tests require OpenCode; fixture agent definitions come from this package.
No model calls, non-fixture project mutations or third-party Python dependencies.
"""

import hashlib
import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import shutil
import subprocess
import time
import unittest
from tempfile import TemporaryDirectory
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, ProxyHandler, build_opener


CONFIG = Path(__file__).resolve().parents[1]
SKILLS = CONFIG / "skills"
REQUIRED = {
    "setup-matt-pocock-skills", "grill-with-docs", "grilling", "domain-modeling",
    "to-spec", "to-tickets", "implement", "implement-spec", "tdd", "code-review",
    "codebase-design",
}
ADAPTED = {
    f"{name}/SKILL.md" for name in REQUIRED - {"codebase-design"}
} | {"setup-matt-pocock-skills/issue-tracker-local.md"}


def project_permissions(source):
    """Copy only source rule models; never load or serialize credential fields."""
    text = re.sub(r"(?m)^\s*//[^\n]*\n", "", source.read_text())
    start = re.search(r'"permissions"\s*:\s*\[', text)
    if start is None:
        raise ValueError("Missing permissions array")
    rules, _ = json.JSONDecoder().raw_decode(text, start.end() - 1)
    if not isinstance(rules, list) or not all(
        isinstance(rule, dict) and set(rule) == {"action", "resource", "effect"}
        and all(isinstance(value, str) for value in rule.values())
        and rule["effect"] in {"allow", "deny", "ask"} for rule in rules
    ):
        raise ValueError("Invalid permission rule model")
    return {"permissions": rules}


def wait_for_fixture_agents(request, location, expected, *, now=time.monotonic,
                            pause=time.sleep, timeout=15):
    """Wait for registration on one server; neither partial nor empty is ready."""
    deadline = now() + timeout
    while True:
        try:
            reply = request()
        except Exception:
            raise AssertionError("Fixture agent request failed") from None
        if not isinstance(reply, dict) or not isinstance(reply.get("location"), dict):
            raise AssertionError("Fixture invalid agent reply")
        if reply["location"].get("directory") != location:
            raise AssertionError("Fixture agent Location mismatch")
        records = reply.get("data")
        if not isinstance(records, list) or any(
            not isinstance(record, dict) or not isinstance(record.get("id"), str)
            or not isinstance(record.get("mode"), str)
            or ("system" in record and not isinstance(record["system"], str))
            or not isinstance(record.get("permissions"), list) for record in records
        ):
            raise AssertionError("Fixture invalid agent reply")
        agents = {record["id"]: record for record in records}
        if len(agents) != len(records):
            raise AssertionError("Fixture invalid agent reply")
        if all(name in agents and (agents[name]["mode"], agents[name].get("system", "").strip()) == definition
               for name, definition in expected.items()):
            return agents
        remaining = deadline - now()
        if remaining <= 0:
            raise AssertionError("Fixture agent registration deadline exceeded")
        pause(min(0.05, remaining))


def fixture_environment(location):
    """No inherited config or credential variables reach the private server."""
    return {"PATH": os.environ.get("PATH", os.defpath), "LANG": "C.UTF-8",
            "HOME": str(location), "XDG_CONFIG_HOME": str(location / ".config"),
            "XDG_DATA_HOME": str(location / ".local/share"),
            "XDG_CACHE_HOME": str(location / ".cache"),
            "XDG_STATE_HOME": str(location / ".local/state"),
            "OPENCODE_DISABLE_MODELS_FETCH": "1"}


@contextmanager
def owned_server(binary, location, env):
    password = secrets.token_urlsafe(32)
    process = subprocess.Popen([binary, "serve", "--stdio", "--hostname", "127.0.0.1",
                                "--port", "0"], cwd=location,
                               env={**env, "OPENCODE_PASSWORD": password},
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, bufsize=0)
    try:
        # The private server writes one JSON readiness line on stdout. Never print it.
        deadline = time.monotonic() + 15
        line = b""
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while b"\n" not in line:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise AssertionError("Fixture server readiness deadline exceeded")
                chunk = os.read(process.stdout.fileno(), 4096)
                if not chunk or len(line) + len(chunk) > 4096:
                    raise AssertionError("Fixture server readiness failed")
                line += chunk
        try:
            url = json.loads(line.split(b"\n", 1)[0])["url"]
            parsed = urlsplit(url)
            if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
                    or not parsed.port or parsed.username or parsed.password
                    or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
                raise ValueError("Invalid private endpoint")
        except (ValueError, KeyError, TypeError):
            raise AssertionError("Fixture server returned invalid endpoint") from None
        yield url.rstrip("/"), password
    finally:
        process.stdin.close()  # EOF releases this server's ownership lease.
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        process.stdout.close()


def discover_agents(binary, *, fixture_parent="/tmp/opencode"):
    """Run discovery with a permissions-only config and disposable HOME/Location."""
    with TemporaryDirectory(dir=fixture_parent) as directory:
        location = Path(directory)
        subprocess.run(["git", "init", "-q", str(location)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for parent in location.parents:
            # V2 discovers direct config and .opencode definitions, and compatibility
            # skills from .claude/.agents, even without an ancestor JSON config.
            # Reject each ancestor source root, including dangling symlinks.
            if any((parent / name).exists() or (parent / name).is_symlink()
                   for name in ("opencode.json", "opencode.jsonc", ".opencode", ".claude", ".agents")):
                raise RuntimeError("Fixture Location has an ancestor definition source")
        config = location / ".config/opencode"
        agents = config / "agents"
        agents.mkdir(parents=True)
        (config / "opencode.json").write_text(json.dumps({**project_permissions(CONFIG / "opencode.jsonc"),
                                                          "update": "disable"}))
        for source in (CONFIG / "agents").glob("*.md"):
            shutil.copyfile(source, agents / source.name)
        env = fixture_environment(location)
        expected = {name: ("primary" if name in ("orchestrator", "planner") else "subagent",
                           (CONFIG / "agents" / f"{name}.md").read_text().split("---", 2)[2].strip())
                    for name in ("orchestrator", "planner", "builder", "merger", "tester", "reviewer")}
        with owned_server(binary, location, env) as (url, password):
            opener = build_opener(ProxyHandler({}))
            auth = base64.b64encode(f"opencode:{password}".encode()).decode("ascii")
            address = f"{url}/api/agent?{urlencode({'location[directory]': str(location)})}"
            def request():
                with opener.open(Request(address, headers={"Authorization": f"Basic {auth}"}),
                                 timeout=3) as response:
                    data = response.read(1024 * 1024 + 1)
                    if len(data) > 1024 * 1024:
                        raise ValueError("Oversize private reply")
                    return json.loads(data)
            return wait_for_fixture_agents(request, str(location), expected)


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


def reviewer_preflight(reply, location, head, checks, *, provenance):
    """Project only permission outcomes from an already obtained V2 agent reply.

    Caller must obtain the reply at its actual assigned Location and establish
    HEAD separately. Never return, print, persist or include the reply in errors.
    This is a rule-model check, not a tool execution or a containment guarantee.
    """
    if (not isinstance(reply, dict) or not isinstance(reply.get("location"), dict)
            or reply["location"].get("directory") != location):
        raise AssertionError("Reviewer preflight Location mismatch")
    record = reply.get("data")
    if (not isinstance(record, dict) or record.get("id") != "reviewer"
            or not isinstance(record.get("permissions"), list)
            or not all(isinstance(rule, dict)
                       and set(rule) == {"action", "resource", "effect"}
                       and all(isinstance(value, str) for value in rule.values())
                       and rule["effect"] in {"allow", "deny", "ask"}
                       for rule in record["permissions"])):
        raise AssertionError("Reviewer preflight invalid rule model")
    outcomes = {}
    for action, resource, expected in checks:
        if expected not in {"allow", "deny"}:
            raise AssertionError("Reviewer preflight invalid expectation")
        result = effect({"permissions": record["permissions"]}, action, resource)
        if result != expected:
            raise AssertionError("Reviewer preflight rule mismatch or pending")
        outcomes[f"{action}:{resource}"] = result
    return {"location": location, "head": head, "rules": outcomes,
            "provenance": provenance}


class DiscoveryTransportTests(unittest.TestCase):
    LOCATION = "/tmp/opencode/synthetic-fixture"
    EXPECTED = {"orchestrator": ("primary", "Fixture orchestrator"),
                "planner": ("primary", "Fixture planner"),
                "builder": ("subagent", "Fixture builder"),
                "merger": ("subagent", "Fixture merger"),
                "tester": ("subagent", "Fixture tester"),
                "reviewer": ("subagent", "Fixture reviewer")}

    def response(self, agents, location=None):
        return {"location": {"directory": location or self.LOCATION}, "data": agents}

    def roles(self):
        return [{"id": name, "mode": mode, "system": body, "permissions": []}
                for name, (mode, body) in self.EXPECTED.items()]

    def test_waits_on_one_transport_from_empty_through_builtins_to_source_roles(self):
        responses = [self.response([]), self.response([{"id": "build", "mode": "primary",
                                                      "system": "builtin", "permissions": []}]),
                     self.response(self.roles())]
        clock = [0.0]
        def advance(delay):
            clock[0] += delay
        seen = []
        def request():
            seen.append(len(seen))
            return responses.pop(0)
        agents = wait_for_fixture_agents(request, self.LOCATION, self.EXPECTED,
                                         now=lambda: clock[0], pause=advance, timeout=1)
        self.assertEqual(set(agents), set(self.EXPECTED))
        self.assertEqual(len(seen), 3)

    def test_incomplete_registration_times_out_without_reporting_success(self):
        clock = [0.0]
        with self.assertRaisesRegex(AssertionError, "deadline"):
            wait_for_fixture_agents(lambda: self.response([]), self.LOCATION, self.EXPECTED,
                                    now=lambda: clock[0], pause=lambda delay: clock.__setitem__(0, clock[0] + delay),
                                    timeout=0.1)

    def test_wrong_location_fails_even_with_complete_roles(self):
        with self.assertRaisesRegex(AssertionError, "Location"):
            wait_for_fixture_agents(lambda: self.response(self.roles(), "/tmp/opencode/wrong"),
                                    self.LOCATION, self.EXPECTED)

    def test_malformed_reply_fails_without_echoing_reply(self):
        sentinel = "SYNTHETIC_CREDENTIAL_SENTINEL_03"
        with self.assertRaisesRegex(AssertionError, "invalid agent reply") as caught:
            wait_for_fixture_agents(lambda: {"location": {"directory": self.LOCATION},
                                            "data": sentinel},
                                    self.LOCATION, self.EXPECTED)
        self.assertNotIn(sentinel, str(caught.exception))

    def test_request_error_fails_without_echoing_error(self):
        sentinel = "SYNTHETIC_CREDENTIAL_SENTINEL_04"
        def broken():
            raise OSError(sentinel)
        with self.assertRaisesRegex(AssertionError, "agent request failed") as caught:
            wait_for_fixture_agents(broken, self.LOCATION, self.EXPECTED)
        self.assertNotIn(sentinel, str(caught.exception))


class AssetTests(unittest.TestCase):
    def test_source_approves_only_the_named_delivery_worktree_boundary(self):
        rules = project_permissions(CONFIG / "opencode.jsonc")
        worktrees = "/home/rbl/.local/share/opencode/worktrees/dotfiles-cleanup/*"
        self.assertEqual(effect(rules, "external_directory", worktrees), "allow")
        for external in ("/etc/*", "/home/rbl/other/*", "/tmp/unrelated/*"):
            self.assertNotEqual(effect(rules, "external_directory", external), "allow")
        for protected in ("config.env", "docs/service.pem", "docs/auth.json"):
            self.assertEqual(effect(rules, "edit", protected), "deny")

    def test_synthetic_credentials_never_enter_discovery_fixture(self):
        sentinel = "SYNTHETIC_CREDENTIAL_SENTINEL_01"
        with TemporaryDirectory(dir="/tmp/opencode") as directory:
            source = Path(directory) / "source.jsonc"
            source.write_text(json.dumps({
                "permissions": [{"action": "read", "resource": "*", "effect": "allow"}],
                "mcp": {"servers": {"fake": {"headers": {"Authorization": sentinel}}}},
            }))
            projected = project_permissions(source)
            self.assertTrue("permissions" in projected)
            self.assertFalse(sentinel in json.dumps(projected))
            self.assertFalse("mcp" in projected)

    def test_discovery_is_isolated_from_synthetic_inherited_config(self):
        sentinel = "SYNTHETIC_CREDENTIAL_SENTINEL_02"
        with TemporaryDirectory(dir="/tmp/opencode") as directory:
            original = os.environ.get("OPENCODE_CONFIG_CONTENT")
            os.environ["OPENCODE_CONFIG_CONTENT"] = sentinel
            try:
                env = fixture_environment(Path(directory))
            finally:
                if original is None:
                    os.environ.pop("OPENCODE_CONFIG_CONTENT", None)
                else:
                    os.environ["OPENCODE_CONFIG_CONTENT"] = original
            self.assertEqual(set(env) - {"PATH"}, {"LANG", "HOME", "XDG_CONFIG_HOME",
                                                     "XDG_DATA_HOME", "XDG_CACHE_HOME",
                                                     "XDG_STATE_HOME", "OPENCODE_DISABLE_MODELS_FETCH"})
            self.assertFalse(sentinel in repr(env))
            self.assertEqual(env["HOME"], directory)

    def test_discovery_rejects_ancestor_markdown_agents_without_json_config(self):
        sentinel = "SYNTHETIC_CREDENTIAL_SENTINEL_ANCESTOR"
        with TemporaryDirectory(dir="/tmp/opencode") as directory:
            agents = Path(directory) / ".opencode/agents"
            agents.mkdir(parents=True)
            (agents / "intruder.md").write_text(
                f"---\ndescription: {sentinel}\n---\nSynthetic agent\n")
            with self.assertRaisesRegex(RuntimeError, "ancestor") as caught:
                discover_agents("unused-fixture-binary", fixture_parent=directory)
            self.assertNotIn(sentinel, str(caught.exception))

    def test_discovery_rejects_all_ancestor_config_and_compatibility_sources(self):
        sentinel = "SYNTHETIC_CREDENTIAL_SENTINEL_COMPATIBILITY"
        for source in ("opencode.json", "opencode.jsonc", ".claude", ".agents"):
            with self.subTest(source=source), TemporaryDirectory(dir="/tmp/opencode") as directory:
                root = Path(directory) / source
                if source.startswith("."):
                    skills = root / "skills" / "intruder"
                    skills.mkdir(parents=True)
                    (skills / "SKILL.md").write_text(
                        f"---\nname: intruder\ndescription: {sentinel}\n---\nSynthetic skill\n")
                else:
                    root.write_text(json.dumps({"mcp": {"servers": {"fake": sentinel}}}))
                with self.assertRaisesRegex(RuntimeError, "ancestor") as caught:
                    discover_agents("unused-fixture-binary", fixture_parent=directory)
                self.assertNotIn(sentinel, str(caught.exception))

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

    def test_preflight_rejects_wrong_location_or_denial_without_echoing_reply(self):
        sentinel = "SYNTHETIC_CREDENTIAL_SENTINEL_PREFLIGHT"
        rules = [{"action": "shell", "resource": "git worktree list --porcelain", "effect": "allow"}]
        reply = {"location": {"directory": "/tmp/opencode/assigned"},
                 "data": {"id": "reviewer", "permissions": rules, "system": sentinel}}
        checks = (("shell", "git worktree list --porcelain", "allow"),
                  ("shell", "git push origin main", "deny"))
        rules.append({"action": "shell", "resource": "*", "effect": "deny"})
        rules.append({"action": "shell", "resource": "git worktree list --porcelain", "effect": "allow"})
        provenance = {"source": "candidate", "activation": "not verified",
                      "integration": "not integrated"}
        report = reviewer_preflight(reply, "/tmp/opencode/assigned", "abc123", checks,
                                    provenance=provenance)
        self.assertEqual(report, {"location": "/tmp/opencode/assigned", "head": "abc123",
                                  "rules": {"shell:git worktree list --porcelain": "allow",
                                            "shell:git push origin main": "deny"},
                                  "provenance": provenance})
        self.assertNotIn(sentinel, repr(report))
        for changed in ({**reply, "location": {"directory": "/tmp/opencode/wrong"}},
                        {**reply, "data": {"id": "reviewer", "permissions": []}},
                        {**reply, "data": {"id": "reviewer", "permissions": sentinel}}):
            with self.assertRaises(AssertionError) as caught:
                reviewer_preflight(changed, "/tmp/opencode/assigned", "abc123", checks,
                                   provenance=provenance)
            self.assertNotIn(sentinel, str(caught.exception))
        with self.assertRaisesRegex(AssertionError, "mismatch"):
            reviewer_preflight(reply, "/tmp/opencode/assigned", "abc123",
                               (("shell", "git worktree add /tmp/opencode/other HEAD", "allow"),),
                               provenance=provenance)


@unittest.skipUnless(shutil.which("opencode"), "OpenCode V2 required for discovery")
class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agents = discover_agents(shutil.which("opencode"))

    def test_reviewer_scoped_read_only_inspection_and_safe_evidence(self):
        reviewer = self.agents["reviewer"]
        permitted = (
            "pwd", "git rev-parse --show-toplevel", "git rev-parse HEAD",
            "git worktree list --porcelain", "git merge-base --is-ancestor 668b23b HEAD",
            "git for-each-ref --format='%(refname) %(objectname)' "
            "refs/heads/feature/cleanup-common-nvim-20261009-a "
            "refs/heads/ticket/cleanup-common-nvim-01-20261009-a "
            "refs/heads/ticket/cleanup-common-nvim-02-20261009-a "
            "refs/heads/ticket/cleanup-common-nvim-03-20261009-a "
            "refs/heads/ticket/cleanup-common-nvim-04-20261009-a",
            "sha256sum docs/plans/common/opencode/review-readiness/ticket01-targeted-tool-evidence.json "
            "docs/plans/common/opencode/review-readiness/repair01-targeted-tool-evidence.json "
            "docs/plans/common/opencode/review-readiness/repair02-targeted-tool-evidence.json",
        )
        for command in permitted:
            self.assertEqual(effect(reviewer, "shell", command), "allow", command)
        checksum = permitted[-1]
        refs = permitted[-2]
        for command in ("find docs -name AGENTS.md", "git worktree add /tmp/opencode/other HEAD",
                        "git worktree remove /tmp/opencode/other", "git worktree prune",
                        "git add file", "git commit -m test", "git push origin feature/x",
                        "git for-each-ref", refs + " --count=5", refs + " > /tmp/opencode/out",
                        "sha256sum /tmp/opencode/unrelated.json", checksum.replace("repair02", "other"),
                        checksum + " /tmp/opencode/extra", checksum + " > /tmp/opencode/out"):
            self.assertNotEqual(effect(reviewer, "shell", command), "allow", command)
        self.assertEqual(effect(reviewer, "read", "config.env"), "deny")
        self.assertEqual(effect(reviewer, "edit", "src/example.py"), "deny")


    def test_fixture_role_discovery(self):
        for name in ("orchestrator", "planner", "builder", "merger", "tester", "reviewer"):
            self.assertIn(name, self.agents)
            expected = "primary" if name in ("orchestrator", "planner") else "subagent"
            self.assertEqual(self.agents[name]["mode"], expected)
            body = (CONFIG / "agents" / f"{name}.md").read_text().split("---", 2)[2].strip()
            self.assertEqual(self.agents[name]["system"].strip(), body,
                             "Fixture must load source agent definitions")

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
            for protected in ("/etc/*", "/etc/ssh/*"):
                self.assertEqual(effect(agent, "external_directory", protected), "deny", name)
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

    def test_loaded_external_boundaries_do_not_grant_unrelated_locations(self):
        worktrees = "/home/rbl/.local/share/opencode/worktrees/dotfiles-cleanup/*"
        for name in ("orchestrator", "builder", "merger", "tester", "reviewer", "planner"):
            agent = self.agents[name]
            self.assertEqual(effect(agent, "external_directory", worktrees), "allow", name)
            for managed in ("/tmp/opencode/*", "/home/rbl/.config/opencode/skills/*",
                            "/home/rbl/.local/share/opencode/tool-output/*",
                            "/home/rbl/.local/share/opencode/shell/*",
                            "/home/rbl/.local/share/opencode/tmp/*"):
                self.assertEqual(effect(agent, "external_directory", managed), "allow",
                                 f"{name}: approved managed directory")
            for unrelated in ("/home/rbl/other/*", "/tmp/unrelated/*",
                              "/home/rbl/.local/share/opencode/other/*",
                              "/home/rbl/.local/share/opencode/worktrees/unrelated/*"):
                self.assertNotEqual(effect(agent, "external_directory", unrelated), "allow",
                                    f"{name}: unrelated external boundary")

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
