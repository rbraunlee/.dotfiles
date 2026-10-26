#!/usr/bin/env python3
"""Report whether a worktree is in use before /ship removes it.

Usage: worktree_in_use.py <worktree-path>
Exit 0: free. Exit 1: in use (reasons printed). Exit 2: could not check.

A worktree is in use when a live Claude Code session's working directory is
inside it (~/.claude/sessions/<pid>.json with a running pid), or when any
process (per lsof) has its current directory inside it.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def session_users(root, sessions_dir):
    users = []
    for file in sorted(sessions_dir.glob("*.json")):
        try:
            data = json.loads(file.read_text())
        except (OSError, ValueError):
            continue
        cwd, pid = data.get("cwd"), data.get("pid")
        if isinstance(pid, int) and cwd and alive(pid) and inside(cwd, root):
            users.append(f"Claude Code session {data.get('name') or pid} (pid {pid}) in {cwd}")
    return users


def process_users(root):
    """Return a list of users, or None when lsof is unavailable or fails."""
    if shutil.which("lsof") is None:
        return None
    out = subprocess.run(["lsof", "-a", "-d", "cwd", "-F", "pcn", "-w"],
                         capture_output=True, text=True, timeout=30)
    if out.returncode not in (0, 1) or not out.stdout:
        return None
    users, pid, command = [], None, None
    for line in out.stdout.splitlines():
        tag, value = line[:1], line[1:]
        if tag == "p":
            pid, command = value, None
        elif tag == "c":
            command = value
        elif tag == "n" and inside(value, root) and pid != str(os.getpid()):
            users.append(f"process {command} (pid {pid}) in {value}")
    return users


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    root = argv[1]
    if not os.path.isdir(root):
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    sessions_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "sessions"
    users = session_users(root, sessions_dir)
    processes = process_users(root)
    if processes is None:
        print("lsof unavailable or failed; cannot confirm the worktree is free", file=sys.stderr)
        for user in users:
            print(user)
        return 1 if users else 2
    users += [p for p in processes if p not in users]
    for user in users:
        print(user)
    return 1 if users else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
