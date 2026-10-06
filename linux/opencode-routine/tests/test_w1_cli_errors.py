"""Input-derived diagnostics must not leak through either CLI execution path."""
from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".local/lib/opencode-routine"))

from routine.cli import error
from routine.contracts import RoutineError, parse_json
import test_w1 as fixtures


class W1DiagnosticTests(unittest.TestCase):
    def test_duplicate_key_error_is_fixed_not_input_derived(self):
        canary = "SECRET_CANARY_W1_DUPLICATE_KEY"
        with self.assertRaises(RoutineError) as caught:
            parse_json('{"' + canary + '":1,"' + canary + '":2}')
        response = error(caught.exception)
        self.assertEqual(response["error"]["code"], "invalid_json")
        self.assertNotIn(canary, str(response))

    def test_io_error_does_not_export_exception_details(self):
        response = error(OSError("SECRET_CANARY_W1_IO"))
        self.assertEqual(response["error"]["code"], "io_error")
        self.assertNotIn("SECRET_CANARY_W1_IO", str(response))

    def test_malformed_request_planning_and_evidence_use_safe_cli_diagnostics(self):
        canary = "SECRET_CANARY_W1_EXPORTED_KEY"
        malformed = '{"' + canary + '":1,"' + canary + '":2}'
        for channel in ("request", "planning", "evidence"):
            with self.subTest(channel=channel):
                fixture = fixtures.W1Tests("test_authorization_and_dispatch_are_explicit_and_idempotent")
                fixture.setUp()
                self.addCleanup(fixture.doCleanups)
                if channel == "request":
                    fixture.cli_authorize()
                    result = fixture.cli("coordinate", "--project", "project", "--feature", "feature",
                                         "--coordinator", "fixture", input=malformed + "\n")
                    response = json.loads(result.stdout.splitlines()[-1])
                else:
                    evidence = fixture.base / "fixture-evidence.json"
                    evidence.write_bytes(fixtures.canonical(fixture.evidence))
                    path = (fixture.root / ".opencode/routine/features/feature/approval.json"
                            if channel == "planning" else evidence)
                    path.write_text(malformed)
                    result = fixture.cli("authorize-local", "--project", "project", "--feature", "feature",
                                         "--root", fixture.root, "--bundle-root", fixture.bundle,
                                         "--api-input", fixture.api, "--configuration-input", fixture.configuration,
                                         "--fixture-evidence", evidence)
                    self.assertEqual(result.returncode, 1)
                    response = json.loads(result.stdout)
                self.assertEqual(response["error"]["code"], "invalid_json")
                self.assertNotIn(canary, result.stdout + result.stderr)
