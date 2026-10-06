"""Owner's W2 entry-point regressions; no live service or project execution."""
import json
from pathlib import Path
import sys
import hashlib
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.local/lib/opencode-routine'))
from routine.launcher import Launcher
from routine.contracts import RoutineError
import test_w1


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_w1.W1Tests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture

    def test_prepare_entry_point_and_repeat_preserve_budget(self):
        auth = self.f.approved()
        with self.f.launcher.coordinator('project', 'feature', 'coordinator') as c:
            self.f.claim(c, auth)
            first = c.local_prepare('run-1')
            self.assertEqual(first['run']['state'], 'local-prepared')
            second = c.local_prepare('run-1')
            self.assertTrue(second['existing'])
            self.assertEqual(first['run'], second['run'])
            self.assertEqual(first['run']['local']['runtime_started_at'],
                             second['run']['local']['runtime_started_at'])

    def test_unassembled_runtime_holds_without_session_or_command(self):
        auth = self.f.approved()
        with self.f.launcher.coordinator('project', 'feature', 'coordinator') as c:
            self.f.claim(c, auth)
            c.local_prepare('run-1')
            started = self.f.store.read()['runs']['project/run-1']['local']['runtime_started_at']
            result = c.local_fixture_check('run-1')
            self.assertEqual(result['run']['state'], 'local-held')
            self.assertFalse(result['run']['local']['sessions'])
            self.assertFalse(result['run']['local']['commands'])
            self.assertEqual(result['run']['local']['runtime_started_at'], started)
            self.assertTrue(c.local_fixture_check('run-1')['existing'])

    def test_stop_does_not_need_coordinator_or_lifecycle_lock(self):
        auth = self.f.approved()
        with self.f.launcher.coordinator('project', 'feature', 'coordinator') as c:
            self.f.claim(c, auth)
        result = self.f.launcher.local_stop('project', 'feature', 'run-1')
        self.assertEqual(result['run']['state'], 'local-held')
        self.assertIsNotNone(result['run']['local']['stop_request'])
        self.assertTrue(self.f.launcher.local_stop('project', 'feature', 'run-1')['existing'])

    def test_stop_request_returns_while_stable_lifecycle_lock_is_held(self):
        auth = self.f.approved()
        with self.f.launcher.coordinator('project', 'feature', 'coordinator') as c:
            self.f.claim(c, auth)
            name = 'local-lifecycle-' + hashlib.sha256(b'project/run-1').hexdigest() + '.lock'
            with self.f.store.lock(name):
                started = time.monotonic()
                response = c.local_stop('run-1')
                self.assertLess(time.monotonic() - started, 1)
                self.assertIsNotNone(response['run']['local']['stop_request'])

    def test_prepare_collision_retains_bytes_and_visible_hold_diagnostics(self):
        auth = self.f.approved()
        artifact = self.f.store.root / 'artifacts' / ('local-' + hashlib.sha256(b'project/run-1').hexdigest())
        artifact.mkdir(mode=0o700)
        marker = artifact / 'unrelated-canary'
        marker.write_bytes(b'never overwrite or adopt')
        with self.f.launcher.coordinator('project', 'feature', 'coordinator') as c:
            self.f.claim(c, auth)
            response = c.local_prepare('run-1')
            self.assertEqual(response['run']['state'], 'local-held')
            self.assertEqual(response['run']['local']['hold_reason'], 'artifact_exists')
            self.assertTrue(c.local_prepare('run-1')['existing'])
        self.assertEqual(marker.read_bytes(), b'never overwrite or adopt')

    def test_typed_cli_preparation_rejects_extra_paths_and_commands(self):
        auth = self.f.cli_authorize()
        dispatch = self.f.cli('authorize-local-dispatch', '--project', 'project', '--feature', 'feature',
                              '--slice', '01', '--dispatch', 'dispatch-1', '--authorization', auth)
        self.assertEqual(dispatch.returncode, 0)
        claim = {'operation': 'local-claim', 'slice_id': '01', 'run_id': 'run-1',
                 'authorization_id': auth, 'dispatch_id': 'dispatch-1',
                 'baseline': self.f.manifest['baseline'], 'execution': 'trusted-local'}
        requests = [claim, {'operation': 'local-prepare', 'run_id': 'run-1', 'path': '/tmp/opencode'},
                    {'operation': 'local-fixture-check', 'run_id': 'run-1', 'argv': ['true']},
                    {'operation': 'local-prepare', 'run_id': 'run-1'}, {'operation': 'status'}]
        response = self.f.cli('coordinate', '--project', 'project', '--feature', 'feature',
                              '--coordinator', 'coordinator', input=''.join(json.dumps(r)+'\n' for r in requests))
        values = [json.loads(line) for line in response.stdout.splitlines()]
        self.assertEqual(response.returncode, 0)
        self.assertIn('error', values[2])
        self.assertIn('error', values[3])
        self.assertEqual(values[4]['run']['state'], 'local-prepared')
        self.assertEqual(values[5]['slices']['01']['state'], 'local-prepared')

    def test_historical_run_refused_before_local_helper(self):
        self.f.historical_fixture()
        with self.f.launcher.coordinator('project', 'historical', 'old-coordinator') as c:
            with self.assertRaises(RoutineError) as caught:
                c.local_prepare('old-run')
            self.assertEqual(caught.exception.code, 'execution_mismatch')
