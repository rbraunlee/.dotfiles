"""Offline durable adapter checkpoint integration; no runtime side effects."""
from copy import deepcopy
import tempfile
import unittest

import test_m2 as fixtures
from test_m2_environment import EnvironmentTests
from routine.checkpoints import EnvironmentCheckpoint, InspectionLedger
from routine.contracts import RoutineError, canonical
from routine.retention_lifecycle import InspectionRequest
from routine.store import Store


class InspectionCheckpointTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory(dir='/tmp/opencode', prefix='routine-inspection-journal-')
        self.addCleanup(root.cleanup)
        self.store = Store(root.name)
        self.request = InspectionRequest('project', 'feature', 'run')
        self.run = {'request': self.request.as_dict(), 'container_id': 'a' * 64, 'state': 'sandbox-failed'}
        with self.store.lock('ledger.lock'):
            self.store.write({'version': 1, 'features': {}, 'runs': {'project/run': self.run}})
        self.record = {'inspection_id': 'b' * 32, 'request': self.request.as_dict(), 'state': 'preparing'}

    def test_dedicated_records_preserve_baseline_and_refuse_reuse(self):
        journal = InspectionLedger(self.store, self.request, lambda request, timeout: True)
        journal(self.record)
        with journal.source_lease(self.request, 5) as lease:
            self.assertTrue(lease.external_admin_excluded)
            self.assertEqual(journal.read_run(self.request, 5), self.run)
        journal({**self.record, 'state': 'inspection-passed'})
        self.assertEqual(self.store.read()['runs']['project/run'], self.run)
        with self.assertRaises(RoutineError):
            journal(self.record)
        with self.assertRaises(RoutineError):
            InspectionLedger(self.store, self.request)({**self.record, 'inspection_id': 'c' * 32})

    def test_default_lease_refuses_admin_exclusion(self):
        journal = InspectionLedger(self.store, self.request)
        journal(self.record)
        with self.assertRaises(RoutineError):
            with journal.source_lease(self.request, 5):
                self.fail('lease must not be granted')

    def test_lease_contends_with_existing_sandbox_lock(self):
        from routine.contracts import digest
        journal = InspectionLedger(self.store, self.request, lambda request, timeout: True)
        journal(self.record)
        with self.store.lock('sandbox-' + digest(b'project/run') + '.lock'):
            with self.assertRaises(RoutineError):
                with journal.source_lease(self.request, 5):
                    self.fail('source lease must not bypass launcher lock')

    def test_unmatched_source_rejected_and_copies_are_independent(self):
        journal = InspectionLedger(self.store, self.request)
        value = journal.read_run(self.request, 5)
        value['state'] = 'changed'
        self.assertEqual(self.store.read()['runs']['project/run'], self.run)
        with self.assertRaises(RoutineError):
            journal.read_run(InspectionRequest('project', 'other', 'run'), 5)


class EnvironmentCheckpointTests(unittest.TestCase):
    write = EnvironmentTests.write
    fixture = EnvironmentTests.fixture
    save_manifest = EnvironmentTests.save_manifest
    authorize = EnvironmentTests.authorize
    prepare_profile = EnvironmentTests.prepare_profile
    git = staticmethod(EnvironmentTests.git)
    writable_fixture = EnvironmentTests.writable_fixture

    def setUp(self):
        from test_m2_environment import environment_profile
        fixtures.M2Tests.setUp(self)
        self.profile = environment_profile()
        self.prepare_profile()

    def test_checkpoint_is_durable_plan_bound_and_terminal_guarded(self):
        from routine.environment import Environment
        from routine.contracts import parse_json
        authorization = self.authorize()
        launcher = self.launcher
        with launcher.coordinator('project', 'feature', 'coord') as session:
            session.claim('01', 'run', authorization)
            Environment().prepare(session, 'run')
            ledger = launcher.store.read()
            run = ledger['runs']['project/run']
            path = launcher.store.root / 'artifacts' / run['environment']['artifact_id'] / 'plan.json'
            plan = parse_json(path.read_bytes())
            sink = EnvironmentCheckpoint(session, 'run', plan)
            event = {'event': 'network-create-intent', 'artifact_id': plan['artifact_id'], 'plan_sha256': run['environment']['plan_sha256']}
            with self.assertRaises(RoutineError):
                sink(event)
            with launcher.store.lock('ledger.lock'):
                ledger['runs']['project/run']['environment']['state'] = 'creating-networks'
                launcher.store.write(ledger)
            sink(event)
            self.assertEqual(launcher.store.read()['runs']['project/run']['environment']['adapter_checkpoints'], [event])
            with self.assertRaises(RoutineError):
                sink({**event, 'plan_sha256': 'f' * 64})


# Imported fixture methods must not rediscover the environment test class here.
del EnvironmentTests
