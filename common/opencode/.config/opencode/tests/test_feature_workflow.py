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
        expected = {name: ("primary" if name in ("orchestrator", "planner", "shipper") else "subagent",
                           (CONFIG / "agents" / f"{name}.md").read_text().split("---", 2)[2].strip())
                    for name in ("orchestrator", "planner", "builder", "merger", "tester", "reviewer",
                                 "shipper")}
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
    def test_planner_proposes_purpose_preserving_mvp_without_mandatory_ceremony(self):
        body = " ".join((CONFIG / "agents/planner.md").read_text().split("---", 2)[2].split())
        for signal in ("smallest useful", "owner requirements", "necessary supporting",
                       "agent recommendations", "significant cuts", "central value",
                       "complete workflow", "vision", "deferred", "targeted question",
                       "no interview", "no graph", "explicit", "fresh scope agreement"):
            with self.subTest(signal=signal):
                self.assertIn(signal, body)
        self.assertNotIn("Obtain approval of the spec and graph", body)

    def test_brainstorm_uses_context_and_respects_requested_depth(self):
        body = " ".join((SKILLS / "brainstorm/SKILL.md").read_text().split("---", 2)[2].split())
        for signal in ("primary conversation", "known", "only when useful", "requested depth",
                       "broad or deep", "possibilities", "not approved requirements",
                       "converge", "owner"):
            with self.subTest(signal=signal):
                self.assertIn(signal, body)
        for compulsory in ("After all setup answers are collected", "Ask the user to confirm before starting",
                           "Default to continuing exploration unless the user asks to wrap up",
                           "ideally 50–100+", "Every ~10 ideas"):
            with self.subTest(compulsory=compulsory):
                self.assertNotIn(compulsory, body)

    def test_grilling_tests_usefulness_without_exhaustive_frontier(self):
        grilling = " ".join((SKILLS / "grilling/SKILL.md").read_text().split("---", 2)[2].split())
        wrapper = " ".join((SKILLS / "grill-with-docs/SKILL.md").read_text().split("---", 2)[2].split())
        for signal in ("useful", "distinctive", "existing tools", "requested",
                       "materially change", "reversibility", "bounded", "deep"):
            with self.subTest(signal=signal):
                self.assertIn(signal, grilling)
        for obsolete in ("Ask the whole frontier", "Word each question so \"yes\" accepts",
                         "frontier is empty", "every branch of the design tree visited"):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, grilling)
        self.assertIn("consequential", wrapper)
        self.assertIn("no interview", wrapper)
        self.assertIn("optional", wrapper)

    def test_spec_and_ticket_guidance_keep_deferred_ideas_nonbinding(self):
        spec = " ".join((SKILLS / "to-spec/SKILL.md").read_text().split("---", 2)[2].split())
        tickets = " ".join((SKILLS / "to-tickets/SKILL.md").read_text().split("---", 2)[2].split())
        for signal in ("vision", "current scope", "exclusions", "deferred",
                       "not acceptance criteria", "current behavior", "fresh scope agreement"):
            with self.subTest(spec=signal):
                self.assertIn(signal, spec)
        for signal in ("only when", "complete workflow", "delivery order",
                       "actual dependencies", "deferred", "not tickets"):
            with self.subTest(tickets=signal):
                self.assertIn(signal, tickets)
        self.assertNotIn("Any prefactoring should be done first", tickets)

    def test_adaptation_provenance_distinguishes_local_brainstorm_from_vendored_skills(self):
        provenance = (CONFIG / "workflow/UPSTREAM.md").read_text()
        self.assertIn("brainstorm", provenance)
        self.assertIn("local", provenance)
        self.assertIn("MVP", provenance)
        self.assertIn("grilling", provenance)
        self.assertIn("deferred", provenance)

    def test_ship_is_registered_as_local_skill_and_ends_delivery_handoffs(self):
        provenance = " ".join((CONFIG / "workflow/UPSTREAM.md").read_text().split())
        for signal in ("`ship`", "/ship", "not from this snapshot", "Ship mode",
                       "command text, not the current branch"):
            with self.subTest(provenance=signal):
                self.assertIn(signal, provenance)
        handoff = "after human QA, run `/ship <feature>`"
        for path in ("implement-spec/LOCAL-EXECUTION.md", "implement/SKILL.md"):
            with self.subTest(handoff=path):
                self.assertIn(handoff, " ".join((SKILLS / path).read_text().split()))
        graph = " ".join((SKILLS / "implement-spec/SKILL.md").read_text().split())
        self.assertNotIn("retain the branch/traceability", graph)
        self.assertIn("delete its ticket branch with `git branch -d`", graph)
        self.assertIn("Keep the feature worktree for QA", graph)

    def test_local_delivery_contract_uses_scoped_agent_commit_attribution(self):
        contract = (SKILLS / "implement-spec/LOCAL-EXECUTION.md").read_text()
        for required in (
            "OpenCode Agent <opencode-agent@users.invalid>",
            "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME",
            "GIT_COMMITTER_EMAIL", "Agent: OpenCode / <actual model name>",
            "git -c commit.gpgsign=false commit", "per command",
            "personal signing key", "global or shared", "rewrite", "existing attribution",
        ):
            with self.subTest(required=required):
                self.assertIn(required, contract)

    def test_commit_creating_roles_read_shared_attribution_contract(self):
        for role in ("orchestrator", "builder", "merger", "refactorer", "cleaner", "shipper"):
            with self.subTest(role=role):
                body = (CONFIG / "agents" / f"{role}.md").read_text().split("---", 2)[2]
                self.assertIn("LOCAL-EXECUTION.md", body)
                self.assertIn("agent-created commits", body)

    def test_merge_commit_example_scopes_identity_and_own_model_trailer(self):
        contract = (SKILLS / "implement-spec/LOCAL-EXECUTION.md").read_text()
        self.assertRegex(contract, re.compile(
            r"GIT_AUTHOR_NAME='OpenCode Agent' GIT_AUTHOR_EMAIL='opencode-agent@users.invalid'"
            r"\s*\\\s*GIT_COMMITTER_NAME='OpenCode Agent' "
            r"GIT_COMMITTER_EMAIL='opencode-agent@users.invalid'\s*\\\s*"
            r"git -c commit.gpgsign=false merge --no-ff --no-gpg-sign .*?"
            r"-m \$'Merge .*?\\n\\nAgent: OpenCode / <actual model name>'"))

    def test_reviewer_guidance_accepts_verified_owner_authorized_tester_preflight(self):
        guidance = (CONFIG / "agents/reviewer.md").read_text().split("---", 2)[2]
        self.assertIn("owner explicitly authorizes", guidance)
        self.assertIn("independent Tester", guidance)
        self.assertIn("actual assigned Location", guidance)
        self.assertIn("immutable review SHA", guidance)
        self.assertIn("source revision", guidance)
        self.assertIn("source versus local", guidance)
        self.assertIn("including any local override", guidance)
        self.assertIn("required positive and negative strict-deny checks", guidance)
        self.assertIn("Reviewer self-query is not mandatory", guidance)
        self.assertIn("Missing, mismatched, stale or unverified", guidance)
        self.assertIn("Coordinator conclusion", guidance)

    def test_reviewer_guidance_keeps_own_inspection_without_unrelated_prerequisites(self):
        text = (CONFIG / "agents/reviewer.md").read_text()
        body = text.split("---", 2)[2]
        self.assertIn("Even with independent Tester evidence", body)
        for required in ("session_move", "Git root, branch and exact final HEAD",
                         "git worktree list --porcelain", "git merge-base --is-ancestor",
                         "complete direct baseline-to-final", "original safe process evidence",
                         "Standards and Spec", "any new denial"):
            self.assertIn(required, body)
        self.assertNotIn("exact five-ref", body)
        self.assertNotIn("literal three-file", body)
        self.assertIn("only when applicable", body)
        self.assertIn("do not spawn nested reviewers", body)
        self.assertIn("Never edit, run project", body)

    def test_reviewer_guidance_reports_scoped_owner_incident_exception_honestly(self):
        body = " ".join((CONFIG / "agents/reviewer.md").read_text().split("---", 2)[2].split())
        for required in ("explicit recorded owner requirement or exception disposition",
                         "only at its declared scope", "unresolved credential incident",
                         "nonblocking under an explicit owner exception",
                         "not remediated, safe, or clean security history",
                         "historical finding, evidence and TODO", "human QA and main merge",
                         "Source correctness or a green rule model cannot clear",
                         "mandatory higher-priority permission policy", "arbitrary waiver"):
            self.assertIn(required, body)
        self.assertIn("Do not read credential values, raw configuration, dumps or affected raw exports", body)

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
                     "to-tickets", "implement", "implement-spec", "ship"):
            path = CONFIG / "commands" / f"{name}.md"
            text = path.read_text()
            self.assertIn("subagent: false", frontmatter(path))
            self.assertIn("$ARGUMENTS", text)
            self.assertNotIn("!`", text)  # No permission-bypassing shell expansion.
            expected = ("orchestrator" if name.startswith("implement")
                        else "shipper" if name == "ship" else "planner")
            self.assertIn(f"agent: {expected}", frontmatter(path))

    def test_ship_command_loads_owner_invoked_primary_shipper(self):
        command = (CONFIG / "commands/ship.md").read_text()
        self.assertIn("Load `ship`", command)
        self.assertIn("not QA approval", command)
        shipper = CONFIG / "agents/shipper.md"
        self.assertRegex(frontmatter(shipper), r"(?m)^mode: primary$")
        entry = SKILLS / "ship/SKILL.md"
        self.assertIn("name: ship", frontmatter(entry))
        self.assertIn("description:", frontmatter(entry))
        body = " ".join(shipper.read_text().split("---", 2)[2].split())
        for signal in ("explicit QA approval", "git merge --abort", "command text, not the current branch",
                       "Merger legitimately runs `git merge --no-ff`", "not containment",
                       "env-prefixed, `git -c` or `git -C` forms",
                       "including pushes to `main`, `switch`/`checkout -B` of `main`"):
            with self.subTest(agent=signal):
                self.assertIn(signal, body)
        rules = " ".join(frontmatter(shipper).split())
        self.assertIn("Records only (guidance: shell stays default-allow", rules)

    def ship_skill(self):
        return " ".join((SKILLS / "ship/SKILL.md").read_text().split("---", 2)[2].split())

    def test_ship_preflight_is_read_only_and_stops_on_any_mismatch(self):
        skill = self.ship_skill()
        for signal in ("read-only", "tested/reviewed SHA", "equals the feature branch tip",
                       "git worktree list --porcelain", "branch is `main`", "primary checkout",
                       "never from inside the feature worktree", "clean",
                       "stop and change nothing", "Never `git switch` or `git checkout` `main`"):
            with self.subTest(signal=signal):
                self.assertIn(signal, skill)

    def test_ship_preflight_stops_when_main_moved_since_verification(self):
        # A merge onto a moved main is untested and goes live via Stow.
        skill = self.ship_skill()
        for signal in ("git merge-base --is-ancestor main <feature-branch>",
                       "main moved since the feature was verified", "untested",
                       "rebase and re-verify"):
            with self.subTest(signal=signal):
                self.assertIn(signal, skill)
        self.assertLess(skill.index("git merge-base --is-ancestor main"),
                        skill.index("stop and change nothing"))

    def test_ship_requires_explicit_owner_qa_approval_after_stated_steps(self):
        skill = self.ship_skill()
        for signal in ("QA checklist", "live configs", "symlink into the primary checkout",
                       "live immediately", "re-stow", "question tool", "explicit approval",
                       "Invoking `/ship` alone is not QA approval", "anything else"):
            with self.subTest(signal=signal):
                self.assertIn(signal, skill)
        self.assertLess(skill.index("explicit approval"),
                        skill.index("git -c commit.gpgsign=false merge --no-ff"))

    def test_ship_merge_is_attributed_no_ff_and_aborts_on_conflict(self):
        skill = self.ship_skill()
        for signal in ("git -c commit.gpgsign=false merge --no-ff --no-gpg-sign",
                       "GIT_COMMITTER_EMAIL='opencode-agent@users.invalid'",
                       "Agent: OpenCode / <actual model name>", "LOCAL-EXECUTION.md",
                       "merge.ff=only", "Conventional Commit", "git merge --abort",
                       "never resolve conflicts on `main`", "Never push `main`"):
            with self.subTest(signal=signal):
                self.assertIn(signal, skill)

    def test_ship_retires_records_first_then_non_force_cleanup(self):
        skill = self.ship_skill()
        retire = skill[skill.index("## 5. Retire"):]
        order = ("`decisions.md` and `approval.md`", "sha256sum", "docs/plans/README.md",
                 "non-force `git worktree remove", "`git branch -d`")
        positions = [retire.index(signal) for signal in order]
        self.assertEqual(positions, sorted(positions), order)
        for signal in ("gitignored", "never `-D`", "never `--force`", "live OpenCode session",
                       "kept and reported", "owned and unambiguous"):
            with self.subTest(signal=signal):
                self.assertIn(signal, skill)

    def test_ship_retire_never_overwrites_primary_decision_records(self):
        # docs/ is gitignored: an overwritten primary record is unrecoverable.
        skill = self.ship_skill()
        for signal in ("Never overwrite", "target is missing", "copy it and verify with `sha256sum`",
                       "identical", "exists and differs", "stop retiring",
                       "keep the worktree and branches", "report both paths",
                       "do not merge their contents"):
            with self.subTest(signal=signal):
                self.assertIn(signal, skill)
        self.assertLess(skill.index("exists and differs"), skill.index("non-force `git worktree remove"))

    def test_ship_reports_after_merge_steps(self):
        skill = self.ship_skill()
        for signal in ("merge SHA", "commits ahead of", "you push", "live configs changed",
                       "stow -R -t ~ -d <group> <package>", "hyprctl reload", "tmux source-file",
                       "restart", "kept and why"):
            with self.subTest(signal=signal):
                self.assertIn(signal, skill)

    def test_ship_pr_mode_is_idempotent_and_the_only_pr_owner(self):
        skill = self.ship_skill()
        view = "gh pr view <feature-branch> --json state,headRefOid,mergeCommit,url"
        cases = ("No PR:", "Open PR:", "Merged PR:")
        for signal in (view, *cases, "`gh pr create` once", "do not create another",
                       "`headRefOid` equals the recorded tested SHA", "update local `main`",
                       "merging the PR was the QA approval", "squash or rebase",
                       "kept and reported (expected)"):
            with self.subTest(signal=signal):
                self.assertIn(signal, skill)
        positions = [skill.index(view)] + [skill.index(case) for case in cases]
        self.assertEqual(positions, sorted(positions))
        # Exactly one PR owner: delivery hands off, /ship creates the feature PR.
        owner = "`/ship` creates the one feature PR after human QA"
        for path in ("implement-spec/LOCAL-EXECUTION.md", "implement-spec/SKILL.md"):
            text = " ".join((SKILLS / path).read_text().split())
            with self.subTest(owner=path):
                self.assertIn(owner, text)
                self.assertNotIn("create/update **one** feature PR", text)

    def test_ship_mode_comes_from_project_profile(self):
        skill = self.ship_skill()
        for signal in ("`Ship mode: local-merge | pr`", "docs/agents/project.md", "missing",
                       "stop and ask", "push only the feature branch", "gh pr create",
                       "only after the PR is merged", "never `gh pr merge`"):
            with self.subTest(signal=signal):
                self.assertIn(signal, skill)
        setup = " ".join((SKILLS / "setup-matt-pocock-skills/SKILL.md").read_text().split())
        template = (SKILLS / "setup-matt-pocock-skills/project.md").read_text()
        self.assertIn("Ship mode", setup)
        self.assertIn("Ship mode: local-merge | pr", template)

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

    def test_reviewer_routine_inspection_without_historical_evidence_grants(self):
        reviewer = self.agents["reviewer"]
        permitted = (
            "pwd", "git rev-parse --show-toplevel", "git branch --show-current",
            "git rev-parse HEAD", "git status --short", "git diff 668b23b f00d123",
            "git worktree list --porcelain", "git merge-base --is-ancestor 668b23b HEAD",
        )
        for command in permitted:
            self.assertEqual(effect(reviewer, "shell", command), "allow", command)
        unassigned_refs = ("git for-each-ref --format='%(refname) %(objectname)' "
                           "refs/heads/feature/other-feature")
        unassigned_checksum = "sha256sum docs/other-feature/evidence.json"
        for command in ("find docs -name AGENTS.md", "git worktree add /tmp/opencode/other HEAD",
                         "git worktree remove /tmp/opencode/other", "git worktree prune",
                         "git add file", "git commit -m test", "git push origin feature/x",
                         "git for-each-ref", unassigned_refs,
                         unassigned_refs + " --count=5", unassigned_refs + " > /tmp/opencode/out",
                         unassigned_checksum, "sha256sum /tmp/opencode/unrelated.json",
                         "git diff 668b23b f00d123 > /tmp/opencode/out",
                         "git diff --output=/tmp/opencode/out 668b23b f00d123"):
            self.assertEqual(effect(reviewer, "shell", command), "deny", command)
        self.assertEqual(effect(reviewer, "read", "config.env"), "deny")
        self.assertEqual(effect(reviewer, "edit", "src/example.py"), "deny")

    def test_preflight_applies_only_assigned_evidence_and_blocks_missing_required_evidence(self):
        location = "/tmp/opencode/assigned-review"
        reply = {"location": {"directory": location}, "data": self.agents["reviewer"]}
        routine = (("shell", "pwd", "allow"),
                   ("shell", "git status --short", "allow"),
                   ("shell", "git worktree list --porcelain", "allow"),
                   ("shell", "git merge-base --is-ancestor base123 tip456", "allow"),
                   ("shell", "git diff base123 tip456", "allow"),
                   ("shell", "git push origin feature/x", "deny"),
                   ("external_directory", "/tmp/unrelated/*", "deny"))
        provenance = {"tester": "independent", "source": "revision", "active": "verified"}
        result = reviewer_preflight(reply, location, "tip456", routine, provenance=provenance)
        self.assertEqual(result["head"], "tip456")
        self.assertEqual(len(result["rules"]), len(routine))
        self.assertNotIn("sha256sum", repr(result))
        with self.assertRaisesRegex(AssertionError, "mismatch or pending"):
            reviewer_preflight(reply, location, "tip456",
                               routine + (("shell", "sha256sum docs/this-feature/evidence.json", "allow"),),
                               provenance=provenance)
        with self.assertRaisesRegex(AssertionError, "Location mismatch"):
            reviewer_preflight(reply, "/tmp/opencode/other", "tip456", routine,
                               provenance=provenance)


    def test_shipper_rules_for_plain_command_forms(self):
        # Plain (unprefixed) command text only; see the known-limit test below.
        shipper = self.agents["shipper"]
        for command in ("git merge --no-ff feature/x", "git merge --no-ff --no-gpg-sign feature/x -m 'feat: x'",
                        "git merge --abort", "git worktree list --porcelain",
                        "git worktree remove /tmp/opencode/feature", "git branch -d feature/x"):
            self.assertEqual(effect(shipper, "shell", command), "allow", command)
        for command in ("git merge feature/x", "git merge --squash feature/x",
                        "git push origin feature/x", "gh pr create --fill"):
            self.assertEqual(effect(shipper, "shell", command), "ask", command)
        for command in ("gh pr merge 12", "gh pr merge 12 --merge --delete-branch",
                        "git push origin main", "git push origin HEAD:main", "git switch main",
                        "git checkout main", "git branch -D feature/x", "git branch -D main",
                        "git worktree remove --force /tmp/opencode/feature",
                        "git worktree remove -f /tmp/opencode/feature"):
            self.assertEqual(effect(shipper, "shell", command), "deny", command)
        self.assertEqual(effect(shipper, "subagent", "explore"), "allow")
        for name in ("builder", "merger", "general", "orchestrator"):
            self.assertEqual(effect(shipper, "subagent", name), "deny", name)
        self.assertEqual(effect(shipper, "edit", "docs/plans/README.md"), "allow")
        for path in ("common/tmux/.config/tmux/tmux.conf", "docs/plans/x/.env", "docs/plans/auth.json"):
            self.assertEqual(effect(shipper, "edit", path), "deny", path)

    def test_shipper_known_limit_prefixed_forms_are_not_blocked(self):
        # Known limit, pinned on purpose: env-prefixed, `git -c` and `git -C` forms
        # are different command text, so pre-existing global rules allow them for
        # the shipper. The attributed ship merge is allowed by that default too,
        # not by the `git merge --no-ff *` rule. The prompt and review are the
        # guardrail. If a rule change starts blocking these, this test fails so
        # the ship merge template and shipper.md limit wording get revisited.
        shipper = self.agents["shipper"]
        attributed = ("GIT_AUTHOR_NAME='OpenCode Agent' GIT_AUTHOR_EMAIL='opencode-agent@users.invalid' "
                      "GIT_COMMITTER_NAME='OpenCode Agent' GIT_COMMITTER_EMAIL='opencode-agent@users.invalid' "
                      "git -c commit.gpgsign=false merge --no-ff --no-gpg-sign feature/x "
                      "-m $'feat(tmux): ship x\\n\\nAgent: OpenCode / Example'")
        for command in (attributed, "GIT_AUTHOR_NAME=x git merge feature/x",
                        "git -c x=y merge --squash feature/x", "git -c x=y push origin main",
                        "GIT_AUTHOR_NAME=x git push origin main",
                        "git -C /home/rbl/.dotfiles switch main", "git switch -C main",
                        "git checkout -B main origin/main", "git branch --delete --force x"):
            with self.subTest(command=command):
                self.assertEqual(effect(shipper, "shell", command), "allow")

    def test_ship_rules_do_not_break_feature_integration(self):
        # Shell rules match command text, not the checked-out branch: Merger keeps
        # its feature-branch merges and Implementers stay unable to merge.
        for command in ("git merge --no-ff ticket/example", "git merge ticket/example"):
            self.assertEqual(effect(self.agents["merger"], "shell", command), "allow", command)
        self.assertEqual(effect(self.agents["builder"], "shell", "git merge --no-ff ticket/x"), "deny")

    def test_fixture_role_discovery(self):
        for name in ("orchestrator", "planner", "builder", "merger", "tester", "reviewer", "shipper"):
            self.assertIn(name, self.agents)
            expected = "primary" if name in ("orchestrator", "planner", "shipper") else "subagent"
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
        for name in ("orchestrator", "builder", "merger", "tester", "reviewer", "planner", "shipper"):
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
        for name in ("orchestrator", "builder", "merger", "tester", "reviewer", "planner", "shipper"):
            agent = self.agents[name]
            self.assertEqual(effect(agent, "external_directory", worktrees), "allow", name)
            for managed in ("/tmp/opencode/*", "/home/rbl/.config/opencode/*",
                            "/home/rbl/.local/share/opencode/tool-output/*",
                            "/home/rbl/.local/share/opencode/shell/*",
                            "/home/rbl/.local/share/opencode/tmp/*"):
                self.assertEqual(effect(agent, "external_directory", managed), "allow",
                                 f"{name}: approved managed directory")
            for unrelated in ("/home/rbl/other/*", "/tmp/unrelated/*",
                              "/home/rbl/.local/share/opencode/other/*",
                              "/home/rbl/.local/share/opencode/worktrees/unrelated/*"):
                expected = "deny" if name == "reviewer" else "ask"
                self.assertEqual(effect(agent, "external_directory", unrelated), expected,
                                 f"{name}: unrelated external boundary")

    def test_reviewer_protected_read_requires_both_read_and_directory_approval(self):
        reviewer = self.agents["reviewer"]
        # A direct read allow must not override a denied external directory boundary.
        self.assertEqual(effect(reviewer, "read", "/etc/hosts"), "allow")
        self.assertEqual(effect(reviewer, "external_directory", "/etc/*"), "deny")
        self.assertEqual(effect(reviewer, "read", "docs/README.md"), "allow")
        self.assertEqual(effect(reviewer, "external_directory",
                                "/home/rbl/.local/share/opencode/worktrees/dotfiles-cleanup/*"),
                         "allow")
        self.assertEqual(effect(reviewer, "read", "config.env"), "deny")
        self.assertEqual(effect(reviewer, "edit", "src/example.py"), "deny")
        self.assertEqual(effect(reviewer, "shell", "git push origin main"), "deny")

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
