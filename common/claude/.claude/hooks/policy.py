#!/usr/bin/env python3
"""PreToolUse policy for the Claude Code delivery workflow.

Claude Code permission rules are unordered (deny > ask > allow) and global, so
the parts of the OpenCode rule model that need ordering, per-agent scope or the
current branch live here instead:

* branch-aware protection of `main` for every session;
* per-role shell and edit limits keyed on the hook's `agent_type`;
* delivery roles must work inside a generated (linked) worktree, never the
  primary checkout;
* `.env.*` secrets with the `.env.example` exception (last match wins);
* draw.io MCP tools only for the aligner and brainstormer roles;
* which subagent types the orchestrator, planner and shipper may launch.

The hook only denies or asks; it never returns "allow", so settings rules and
permission modes still apply. Command parsing is best effort: this is a
guardrail for trusted local development, not a sandbox.
"""

import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys

PROTECTED = "main"

DELIVERY_ROLES = {"builder", "merger", "tester", "reviewer", "cleaner", "refactorer"}

# Roles whose shell is limited to an allowlist (every segment must match).
SHELL_ALLOW = {
    "reviewer": [
        ("pwd",), ("cd",), ("man",),
        ("git", "rev-parse"), ("git", "branch", "--show-current"),
        ("git", "status"), ("git", "diff"), ("git", "log"), ("git", "show"),
        ("git", "ls-files"), ("git", "worktree", "list", "--porcelain"),
        ("git", "merge-base", "--is-ancestor"),
    ],
    "recaper": [("pwd",), ("cd",), ("man",), ("git", "log"), ("git", "diff")],
    "aligner": [("man",)],
    "brainstormer": [("man",)],
    "tutor": [("man",)],
}

# Planner: read-only commands pass through, anything else asks.
PLANNER_READ_ONLY = [
    ("pwd",), ("cd",), ("man",), ("ls",),
    ("git", "status"), ("git", "diff"), ("git", "log"), ("git", "show"),
    ("git", "remote", "-v"), ("git", "rev-parse"), ("git", "branch", "--show-current"),
    ("git", "worktree", "list"),
]

# Git subcommands denied per role.
GIT_DENY = {
    "builder": {"merge"},
    "tester": {"add", "commit", "merge", "checkout", "switch"},
}

# Edit allowlists, relative to the edited file's repository root.
EDIT_ALLOW = {
    "aligner": ["docs/**", "CONTEXT.md", "GLOSSARY.md"],
    "brainstormer": ["docs/**"],
    "planner": ["docs/**", "specs/**", ".scratch/**", "AGENTS.md", "CLAUDE.md",
                "CONTEXT.md", "GLOSSARY.md", "GLOSSARY-MAP.md"],
    "shipper": ["docs/plans/**"],
    "tester": [], "reviewer": [], "recaper": [], "tutor": [],
}

DRAWIO_ROLES = {"aligner", "brainstormer"}

# Subagent types each role may launch; roles not listed here are unrestricted
# (the plain main session). Delivery and interview roles also drop the Agent tool.
AGENT_ALLOW = {
    "orchestrator": {"builder", "merger", "tester", "reviewer", "Explore", "general-purpose"},
    "planner": {"Explore"},
    "shipper": {"Explore"},
}
NO_AGENTS = DELIVERY_ROLES | {"aligner", "brainstormer", "recaper", "tutor"}

# Ordered secret rules; the last match wins (mirrors opencode.jsonc).
SECRET_RULES = [
    ("*.env", "deny"), ("*.env.*", "deny"), ("*credentials*", "deny"),
    ("*id_rsa*", "deny"), ("*id_ed25519*", "deny"), ("*.pem", "deny"),
    ("*auth.json", "deny"), ("*.npmrc", "deny"), ("*.pypirc", "deny"),
    ("*.env.example", "allow"),
]

EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}
FILE_TOOLS = EDIT_TOOLS | {"Read"}
WRAPPERS = {"command", "builtin", "exec", "nohup", "time", "env"}
SEPARATORS = {"&&", "||", ";", "|", "&", "|&", ";;", "(", ")", "\n"}


class Decision(Exception):
    def __init__(self, kind, reason):
        super().__init__(reason)
        self.kind = kind
        self.reason = reason


def deny(reason):
    raise Decision("deny", reason)


def ask(reason):
    raise Decision("ask", reason)


# --- git helpers ------------------------------------------------------------

def git(directory, *args):
    try:
        out = subprocess.run(
            ["git", "-C", directory, *args], capture_output=True, text=True,
            timeout=10, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def existing_dir(path):
    path = os.path.abspath(path)
    while path and not os.path.isdir(path):
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent
    return path


def repo_info(path):
    """Return (toplevel, is_primary_checkout, branch) or None outside a repo."""
    directory = existing_dir(path)
    if directory is None:
        return None
    out = git(directory, "rev-parse", "--path-format=absolute",
              "--show-toplevel", "--git-dir", "--git-common-dir")
    if not out:
        return None
    lines = out.splitlines()
    if len(lines) != 3:
        return None
    top, git_dir, common = lines
    primary = os.path.realpath(git_dir) == os.path.realpath(common)
    branch = git(directory, "symbolic-ref", "--short", "-q", "HEAD") or ""
    return top, primary, branch


# --- shell parsing ----------------------------------------------------------

def segments(command):
    """Split a command into simple commands; substitutions become separators."""
    text = command.replace("\\\n", " ").replace("\n", " ; ")
    text = re.sub(r"\$\(|`|<\(|>\(", " ; ", text)
    lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|()<>")
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError:
        deny("Could not parse the shell command; split it into plain commands.")
    current, out = [], []
    redirect = False
    for token in tokens:
        if token in SEPARATORS or set(token) <= set(";&|"):
            if current:
                out.append((current, redirect))
            current, redirect = [], False
        elif set(token) <= set("<>") or token.startswith(">"):
            redirect = redirect or ">" in token
            current.append(token)
        else:
            current.append(token)
    if current:
        out.append((current, redirect))
    return out


def strip_prefix(words):
    """Drop leading VAR=value assignments and transparent wrappers."""
    words = list(words)
    while words:
        head = words[0]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", head):
            words.pop(0)
        elif head in WRAPPERS:
            words.pop(0)
            while words and words[0].startswith("-"):
                words.pop(0)
        else:
            break
    return words


def parse_git(words, directory):
    """Return (directory, subcommand, args) for a git invocation."""
    i = 1
    while i < len(words):
        w = words[i]
        if w == "-C" and i + 1 < len(words):
            directory = os.path.join(directory, os.path.expanduser(words[i + 1]))
            i += 2
        elif w in ("-c", "--git-dir", "--work-tree", "--namespace") and i + 1 < len(words):
            i += 2
        elif w.startswith("-"):
            i += 1
        else:
            return directory, w, words[i + 1:]
    return directory, "", []


def matches_prefix(words, allowed):
    return any(tuple(words[:len(p)]) == p for p in allowed)


def targets_protected(ref):
    ref = ref.lstrip("+")
    dest = ref.split(":", 1)[1] if ":" in ref else ref
    return dest in (PROTECTED, f"refs/heads/{PROTECTED}")


def check_git(sub, args, directory, role):
    flags = [a for a in args if a.startswith("-")]
    positionals = [a for a in args if not a.startswith("-")]
    info = repo_info(directory)
    branch = info[2] if info else ""

    if sub in GIT_DENY.get(role, set()):
        deny(f"The {role} role may not run `git {sub}`.")

    if sub in ("switch", "checkout"):
        before_dashdash = args[:args.index("--")] if "--" in args else args
        names = [a for a in before_dashdash if not a.startswith("-")]
        if "--" not in args and PROTECTED in names:
            deny(f"Agents never switch to `{PROTECTED}`; only the owner-invoked /ship "
                 "works from the primary checkout where it is already checked out.")
        if any(f in flags for f in ("-B", "-C", "--force-create")) and PROTECTED in names:
            deny(f"Resetting `{PROTECTED}` with switch/checkout is not allowed.")

    if sub == "branch":
        forced = any(f in flags for f in ("-f", "--force", "-D", "-M", "-C")) or (
            "--delete" in flags and "--force" in flags)
        if forced and PROTECTED in positionals:
            deny(f"Forcing, moving or deleting `{PROTECTED}` is not allowed.")
        if role == "shipper" and ("-D" in flags or ("--delete" in flags and "--force" in flags)):
            deny("The shipper retires branches with `git branch -d` only, never -D.")

    if sub == "push":
        if any(targets_protected(p) for p in positionals[1:]):
            deny(f"Pushing to `{PROTECTED}` is the owner's job.")
        if any(f in flags for f in ("--all", "--mirror")):
            deny("`git push --all/--mirror` would include the protected branch.")
        if len(positionals) <= 1 and branch == PROTECTED:
            deny(f"A bare `git push` on `{PROTECTED}` would publish it; the owner pushes.")

    if sub == "merge" and "--abort" not in flags:
        if branch == PROTECTED and role != "shipper":
            ask(f"This merges into `{PROTECTED}`. Agents reach `{PROTECTED}` only via "
                "the owner-invoked /ship after explicit QA approval.")
        if role == "shipper" and "--no-ff" not in flags:
            ask("The shipper only creates an attributed `git merge --no-ff`.")

    if sub == "worktree" and positionals[:1] == ["remove"] and role == "shipper":
        if any(f in flags for f in ("-f", "--force")):
            deny("The shipper never force-removes worktrees.")


def check_bash(command, cwd, role):
    directory = cwd
    for words, redirect in segments(command):
        words = strip_prefix(words)
        if not words:
            continue
        program = os.path.basename(words[0])

        if role in SHELL_ALLOW:
            if redirect or any("--output" in w for w in words):
                deny(f"The {role} role is read-only; output redirection is not allowed.")
            if not matches_prefix([program] + words[1:], SHELL_ALLOW[role]):
                deny(f"The {role} role may only run: " + ", ".join(
                    " ".join(p) for p in SHELL_ALLOW[role]) + ".")

        if program == "cd":
            target = os.path.expanduser(words[1]) if len(words) > 1 else os.path.expanduser("~")
            directory = os.path.normpath(os.path.join(directory, target))
            continue

        if program == "gh" and words[1:3] == ["pr", "merge"]:
            deny("The owner merges pull requests; agents never run `gh pr merge`.")

        effective = directory
        if program == "git":
            effective, sub, args = parse_git(words, directory)
            check_git(sub, args, effective, role)

        if role in DELIVERY_ROLES:
            info = repo_info(effective)
            if info and info[1]:
                deny(f"The {role} role works only in its assigned generated worktree. "
                     f"Start every Bash call with `cd '<assigned worktree>' && …`; "
                     f"{effective} is the primary checkout.")

        if role == "planner" and not matches_prefix([program] + words[1:], PLANNER_READ_ONLY):
            ask("The planner asks before running commands that are not read-only.")


# --- file tools -------------------------------------------------------------

def secret_decision(path):
    name = os.path.basename(path)
    result = None
    for pattern, effect in SECRET_RULES:
        if fnmatch.fnmatchcase(name, pattern) or fnmatch.fnmatchcase(path, pattern):
            result = effect
    return result


def check_file(tool, path, cwd, role):
    path = os.path.normpath(os.path.join(cwd, os.path.expanduser(path)))
    if secret_decision(path) == "deny":
        deny(f"{os.path.basename(path)} matches a secret-file rule.")
    if tool not in EDIT_TOOLS:
        return
    info = repo_info(path)
    if role in EDIT_ALLOW:
        allowed = EDIT_ALLOW[role]
        rel = os.path.relpath(path, info[0]) if info else None
        if rel is None or rel.startswith("..") or not any(
                rel == p or (p.endswith("/**") and rel.startswith(p[:-2])) for p in allowed):
            deny(f"The {role} role may only edit: " + (", ".join(allowed) or "nothing") + ".")
    if role in DELIVERY_ROLES and info and info[1]:
        deny(f"The {role} role edits only inside its assigned generated worktree; "
             f"{path} is in the primary checkout.")


def decide(event):
    tool = event.get("tool_name", "")
    data = event.get("tool_input") or {}
    cwd = event.get("cwd") or os.getcwd()
    role = event.get("agent_type") or ""

    if tool.startswith("mcp__drawio__") and role not in DRAWIO_ROLES:
        deny("draw.io opens a browser tab; only the aligner and brainstormer use it.")
    if tool == "Agent":
        kind = data.get("subagent_type") or "general-purpose"
        if role in NO_AGENTS:
            deny(f"The {role} role does not launch agents.")
        if role in AGENT_ALLOW and kind not in AGENT_ALLOW[role]:
            deny(f"The {role} role may only launch: " + ", ".join(sorted(AGENT_ALLOW[role])) + ".")
    elif tool == "Bash":
        check_bash(data.get("command", ""), cwd, role)
    elif tool in FILE_TOOLS:
        path = data.get("file_path") or data.get("notebook_path")
        if path:
            check_file(tool, path, cwd, role)


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        print("policy hook: invalid JSON input", file=sys.stderr)
        return 2
    try:
        decide(event)
    except Decision as decision:
        json.dump({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision.kind,
            "permissionDecisionReason": decision.reason,
        }}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
