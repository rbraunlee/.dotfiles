"""Exercise runner discovery and exit status in disposable repositories."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


RUNNER = Path(__file__).resolve().parents[2] / "run.py"
PASS = "import unittest\nclass Check(unittest.TestCase):\n    def test_ok(self): pass\n"
FAIL = "import unittest\nclass Check(unittest.TestCase):\n    def test_bad(self): self.fail('intentional failure')\n"


class RunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-runner-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "tests").mkdir()
        shutil.copyfile(RUNNER, self.root / "tests/run.py")
        self.opencode = self.root / "common/opencode/.config/opencode/tests"
        self.opencode.mkdir(parents=True)

    def suite(self, relative, source):
        path = self.root / relative
        path.mkdir(parents=True, exist_ok=True)
        (path / "test_example.py").write_text(source)

    def run_fixture(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(self.root / "tests/run.py"), *args],
            cwd=self.root.parent, capture_output=True, text=True, timeout=20,
        )

    def test_default_includes_hidden_suite_and_isolates_same_module_names(self):
        self.suite("tests/common/example", PASS)
        self.suite(str(self.opencode.relative_to(self.root)), FAIL)
        result = self.run_fixture()
        self.assertEqual(result.returncode, 1)
        self.assertIn("2 suites run; 1 failed", result.stdout)
        self.assertIn("intentional failure", result.stderr)

    def test_failure_does_not_prevent_later_suite(self):
        self.suite("tests/common/example", FAIL)
        self.suite(str(self.opencode.relative_to(self.root)), PASS)
        result = self.run_fixture()
        self.assertEqual(result.returncode, 1)
        self.assertIn("=== common/opencode ===", result.stdout)
        self.assertIn("2 suites run; 1 failed", result.stdout)
        self.assertIn("OK", result.stderr)

    def test_empty_suite_and_unknown_selection_fail(self):
        (self.opencode / "test_example.py").write_text("# No test cases\n")
        result = self.run_fixture()
        self.assertEqual(result.returncode, 1)
        self.assertIn("no tests discovered", result.stderr)
        result = self.run_fixture("typo")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown suites: typo", result.stderr)


if __name__ == "__main__":
    unittest.main()
