#!/usr/bin/env python3
"""Run repository suites in separate processes, including package-local tests."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def suites():
    found = {
        str(path.relative_to(ROOT / "tests")): path
        for path in sorted((ROOT / "tests").glob("*/*"))
        if path.is_dir() and any(path.glob("test_*.py"))
    }
    found["common/opencode"] = ROOT / "common/opencode/.config/opencode/tests"
    return found


def run_suite(path):
    suite = unittest.TestLoader().discover(str(path))
    if not suite.countTestCases():
        print(f"ERROR: no tests discovered in {path}", file=sys.stderr)
        return 1
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def main():
    available = suites()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suites", nargs="*", help="suite names; default: all")
    parser.add_argument("--list", action="store_true", help="list available suites")
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.list:
        print("\n".join(available))
        return 0
    if args.worker:
        if args.worker not in available:
            parser.error(f"unknown suite: {args.worker}")
        return run_suite(available[args.worker])
    selected = list(dict.fromkeys(args.suites or available))
    unknown = set(selected) - available.keys()
    if unknown:
        parser.error("unknown suites: " + ", ".join(sorted(unknown)))
    if not selected:
        parser.error("no suites found")
    failed = []
    for name in selected:
        print(f"\n=== {name} ===", flush=True)
        result = subprocess.run(
            [sys.executable, "-B", str(Path(__file__).resolve()), "--worker", name],
            cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if result.returncode:
            failed.append(name)
    print(f"\n{len(selected)} suites run; {len(failed)} failed.", flush=True)
    if failed:
        print("Failed suites: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
