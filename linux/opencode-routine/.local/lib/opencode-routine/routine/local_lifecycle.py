"""W2's sole ledger lifecycle driver; injected runtime, no service discovery."""
from copy import deepcopy
import os
from pathlib import Path
import re
import time
import uuid

from .contracts import RoutineError, canonical, digest, fields, hash_value, identifier, require


TERMINAL = {'local-held', 'local-failed', 'local-fixture-passed'}
ACTIVE = {'local-preparing', 'local-starting', 'local-running', 'local-stopping'}
DIAGNOSTICS = {'command_failed', 'command_timeout', 'stop_uncertain', 'output_omitted'}
HOLD_CODES = {'artifact_exists', 'changed_input', 'unsafe_git', 'unsafe_state',
              'command_timeout', 'output_limit', 'input_limit', 'ownership_uncertain',
              'configuration_unverified', 'stop_uncertain', 'stop_requested',
              'recovery_required', 'inactive_coordinator', 'local_interrupted',
              'adapter_failed', 'invalid_input'}


def local_record(run):
    if 'local' not in run:
        run['local'] = {'version': 1, 'driver': None, 'artifact': None,
                        'runtime_started_at': None, 'runtime_deadline': None,
                        'last_progress_at': None, 'checkpoints': [], 'prepared': None,
                        'configuration': None, 'sessions': [], 'commands': [],
                        'checks': [], 'diagnostics': [], 'stop_request': None}
    return run['local']


def owned_run(launcher, ledger, project_id, feature_id, run_id, coordinator=None):
    identifier(run_id)
    feature = launcher.feature(ledger, launcher.key(project_id, feature_id))
    require(feature.get('execution') == 'trusted-local', 'execution_mismatch',
            'Local operation requires a local feature')
    run = ledger['runs'].get(f'{project_id}/{run_id}')
    require(run is not None, 'unapproved', 'Run must already be claimed')
    require(run.get('execution') == 'trusted-local', 'execution_mismatch', 'Local run required')
    request = run['request']
    require(request['feature_id'] == feature_id and request['project_id'] == project_id,
            'unapproved', 'Run belongs to another feature')
    require(feature['slices'][request['slice_id']]['run_id'] == run_id,
            'identity_conflict', 'Run does not own its slice')
    dispatch = feature['dispatches'].get(request['dispatch_id'])
    require(dispatch and dispatch['dispatch_authorization_id'] == request['dispatch_authorization_id'] and
            dispatch['request']['slice_id'] == request['slice_id'] and
            dispatch['request']['authorization_id'] == request['authorization_id'] and
            dispatch['request']['baseline'] == run['baseline'] and
            feature['authorization_id'] == request['authorization_id'],
            'unapproved', 'Claim authorization changed')
    if coordinator is not None:
        require(coordinator.active and feature['coordinator'] and
                feature['coordinator']['token'] == coordinator.token,
                'inactive_coordinator', 'Coordinator no longer owns the feature')
    return feature, run


def request_stop(launcher, project_id, feature_id, run_id, *, clock=time.time):
    """Stopping-only administration: never acquires or waits for lifecycle lock."""
    with launcher.store.lock('ledger.lock'):
        ledger = launcher.store.read()
        feature, run = owned_run(launcher, ledger, project_id, feature_id, run_id)
        if run['state'] in ('local-fixture-passed', 'local-failed'):
            return {'run': deepcopy(run), 'existing': True}
        local = local_record(run)
        existing = local['stop_request'] is not None or run['state'] in TERMINAL
        if local['stop_request'] is None:
            local['stop_request'] = {'id': uuid.uuid4().hex, 'requested_at': clock()}
        driver = local['driver']
        missing = driver is None
        if driver:
            try:
                os.kill(driver['pid'], 0)
            except ProcessLookupError:
                missing = True
            if local['runtime_deadline'] is not None and clock() > local['runtime_deadline']:
                missing = True
            if clock() > local['stop_request']['requested_at'] + run['command_limits']['command_seconds']:
                missing = True
        if run['state'] not in TERMINAL and missing:
            run['state'] = 'local-held'
            local['hold_reason'] = 'stop_uncertain'
            run['result'] = {'execution': 'trusted-local', 'outcome': 'held',
                             'qualification': None, 'evidence_sha256': None}
            feature['slices'][run['request']['slice_id']]['state'] = run['state']
        launcher.store.write(ledger)
        return {'run': deepcopy(run), 'existing': existing}


class LocalLifecycle:
    def __init__(self, adapter=None, *, clock=time.time, monotonic=time.monotonic,
                 sleep=time.sleep, checkpoint=None):
        self.adapter = adapter
        self.clock, self.monotonic, self.sleep = clock, monotonic, sleep
        self.checkpoint = checkpoint or (lambda _: None)

    def prepare(self, coordinator, run_id):
        return self._drive(coordinator, run_id, fixture=False)

    def fixture_check(self, coordinator, run_id):
        return self._drive(coordinator, run_id, fixture=True)

    def _drive(self, coordinator, run_id, *, fixture):
        launcher = coordinator.launcher
        identifier(run_id)
        run_key = f'{coordinator.project_id}/{run_id}'
        lock_name = 'local-lifecycle-' + digest(run_key.encode()) + '.lock'
        with launcher.store.lock(lock_name, blocking=False):
            with launcher.store.lock('ledger.lock'):
                ledger = launcher.store.read()
                feature, run = owned_run(launcher, ledger, coordinator.project_id,
                                         coordinator.feature_id, run_id, coordinator)
                if run['state'] in TERMINAL or (not fixture and run['state'] == 'local-prepared'):
                    return {'run': deepcopy(run), 'existing': True}
                local = run.get('local') or local_record(deepcopy(run))
                if run['state'] in ACTIVE or local['driver'] is not None or local['stop_request']:
                    local = local_record(run)
                    local['hold_reason'] = 'recovery_required'
                    run['state'] = 'local-held'
                    run['result'] = {'execution': 'trusted-local', 'outcome': 'held',
                                     'qualification': None, 'evidence_sha256': None}
                    feature['slices'][run['request']['slice_id']]['state'] = run['state']
                    launcher.store.write(ledger)
                    return {'run': deepcopy(run), 'existing': True}
                require(not fixture or run['state'] == 'local-prepared', 'recovery_required',
                        'Prepare the clone before fixture execution')
                feature_copy = deepcopy(feature)
                run_copy = deepcopy(run)
            # Expensive validation outside ledger lock and before driver effects.
            launcher._check_local_inputs(feature_copy, run_copy['baseline'])
            driver_id = uuid.uuid4().hex
            with launcher.store.lock('ledger.lock'):
                ledger = launcher.store.read()
                feature, run = owned_run(launcher, ledger, coordinator.project_id,
                                         coordinator.feature_id, run_id, coordinator)
                require(feature['package'] == feature_copy['package'] and run == run_copy,
                        'changed_input', 'Authorization changed during validation')
                reserved = [r for r in ledger['runs'].values() if r.get('execution') == 'trusted-local' and
                            r.get('local', {}).get('driver') is not None]
                require(len(reserved) < 3 and
                        sum(r['request']['project_id'] == coordinator.project_id and
                            r['request']['feature_id'] == coordinator.feature_id for r in reserved) <
                        feature['package']['profile']['concurrency']['workers_per_feature'],
                        'capacity_wait', 'Local driver capacity unavailable; no runtime budget started')
                local = local_record(run)
                local['driver'] = {'id': driver_id, 'coordinator_token': coordinator.token, 'pid': os.getpid()}
                if local['runtime_started_at'] is None:
                    started = self.clock()
                    local['runtime_started_at'] = started
                    local['runtime_deadline'] = started + run['budgets']['slice_seconds']
                    local['last_progress_at'] = started
                local['artifact'] = str(launcher.store.root / 'artifacts' / ('local-' + digest(run_key.encode())))
                run['state'] = 'local-starting' if fixture else 'local-preparing'
                feature['slices'][run['request']['slice_id']]['state'] = run['state']
                launcher.store.write(ledger)
            self.coordinator, self.run_id, self.run_key, self.driver_id = coordinator, run_id, run_key, driver_id
            self.cleanup_deadline = None
            try:
                self._journal('fixture' if fixture else 'preparation', 'intent', {})
                if fixture:
                    self._fixture(feature_copy)
                else:
                    self._prepare(feature_copy)
            except BaseException as exc:
                # A crash can leave an intent without observed identity. Never create again.
                self._failure(exc, fixture=fixture)
                if not isinstance(exc, Exception):
                    raise
            return {'run': self._read(), 'existing': False}

    def _read(self):
        with self.coordinator.launcher.store.lock('ledger.lock'):
            ledger = self.coordinator.launcher.store.read()
            return deepcopy(ledger['runs'][self.run_key])

    def _update(self, change, *, stopping=False):
        c, launcher = self.coordinator, self.coordinator.launcher
        with launcher.store.lock('ledger.lock'):
            ledger = launcher.store.read()
            feature, run = owned_run(launcher, ledger, c.project_id, c.feature_id, self.run_id, c)
            local = local_record(run)
            require(local['driver'] and local['driver']['id'] == self.driver_id and
                    local['driver']['coordinator_token'] == c.token,
                    'recovery_required', 'Stale lifecycle driver cannot publish')
            require(stopping or not local['stop_request'], 'stop_requested', 'Owned work must stop')
            change(run, local)
            feature['slices'][run['request']['slice_id']]['state'] = run['state']
            launcher.store.write(ledger)

    def _journal(self, effect, phase, identity, *, stopping=False):
        # Clone helper is trusted launcher code; only identity keys enter checkpoints.
        keys = {'sha256', 'commit', 'branch', 'path', 'checkout', 'git_dir', 'artifact',
                'bundle_sha256', 'id', 'session_id', 'owner', 'directory', 'driver_id',
                'argv_sha256', 'name'}
        numeric = {k: v for k, v in identity.items() if k in ('deadline', 'device', 'inode', 'bytes') and
                   type(v) in (int, float)}
        identity = {k: v for k, v in identity.items() if k in keys and isinstance(v, str)}
        identity.update(numeric)
        identity['driver_id'] = self.driver_id
        def change(run, local):
            local['checkpoints'].append({'sequence': len(local['checkpoints']) + 1,
                                         'effect': effect, 'phase': phase, 'at': self.clock(),
                                         'identity': identity})
        self._update(change, stopping=stopping)
        self.checkpoint(effect + ':' + phase)

    def _deadline(self, *, seconds=None, cleanup=False):
        run = self._read()
        bound = run['command_limits']['command_seconds'] if seconds is None else seconds
        if not cleanup:
            bound = min(bound, run['local']['runtime_deadline'] - self.clock())
            tracked_live = any(c['status'] == 'running' and c['deadline'] > self.clock()
                               for c in run['local']['commands'])
            if not tracked_live:
                bound = min(bound, run['local']['last_progress_at'] + run['budgets']['inactivity_seconds'] - self.clock())
            require(bound > 0, 'command_timeout', 'Slice budget exhausted')
        else:
            if self.cleanup_deadline is None:
                self.cleanup_deadline = self.monotonic() + bound
            bound = min(bound, self.cleanup_deadline - self.monotonic())
            require(bound > 0, 'stop_uncertain', 'Stopping observation budget exhausted')
        return self.monotonic() + bound

    def _call(self, method, *, cleanup=False, seconds=None, **kwargs):
        if not cleanup:
            self._update(lambda r, l: None)
        deadline = self._deadline(seconds=seconds, cleanup=cleanup)
        value = getattr(self.adapter, method)(deadline=deadline, **kwargs)
        # Late returned identity is handled by caller when possible, but never a pass.
        require(self.monotonic() <= deadline, 'command_timeout', 'Adapter returned after deadline')
        return value

    def _prepare(self, feature):
        from .local_run import prepare_clone
        run = self._read()
        parent = Path(run['local']['artifact']).parent
        require(not parent.is_symlink(), 'unsafe_state', 'Linked artifact root forbidden')
        parent.mkdir(mode=0o700, exist_ok=True)
        self.coordinator.launcher.store._private(parent, directory=True)
        deadline = self._deadline()
        def checkpoint(name, details):
            fields(details, ('phase', 'identity'), 'preparation checkpoint')
            require(details['phase'] in ('intent', 'observed') and isinstance(details['identity'], dict),
                    'invalid_input', 'Invalid preparation checkpoint')
            self._journal(name, details['phase'], details['identity'])
            require(self.monotonic() <= deadline, 'command_timeout', 'Preparation deadline exceeded')
        prepared = prepare_clone(feature, run, Path(run['local']['artifact']),
                                 timeout=max(0, deadline - self.monotonic()),
                                 max_bytes=run['command_limits']['input_bytes'], checkpoint=checkpoint)
        require(self.monotonic() <= deadline, 'command_timeout', 'Preparation deadline exceeded')
        self.coordinator.launcher._check_local_inputs(feature, run['baseline'])
        self._journal('preparation', 'observed', {'commit': prepared['commit'], 'branch': prepared['branch']})
        def change(r, local):
            local['prepared'] = prepared
            local['driver'] = None
            local['last_progress_at'] = self.clock()
            r['state'] = 'local-prepared'
        self._update(change)

    def _session(self, value, *, parent_id=None):
        fields(value, ('id', 'directory', 'parent_id', 'owner'), 'session ownership')
        require(isinstance(value['id'], str) and re.fullmatch(r'ses[A-Za-z0-9_-]{1,125}', value['id']) and
                value['directory'] == self.directory and value['parent_id'] == parent_id and
                value['owner'] == self.run_key, 'ownership_uncertain', 'Session ownership not established')
        return deepcopy(value)

    def _command(self, value, session):
        fields(value, ('id', 'directory', 'session_id', 'owner', 'processes'), 'command ownership')
        require(isinstance(value['id'], str) and re.fullmatch(r'sh_[A-Za-z0-9_-]{1,125}', value['id']) and
                value['directory'] == self.directory and value['session_id'] == session['id'] and
                value['owner'] == self.run_key and isinstance(value['processes'], list) and value['processes'],
                'ownership_uncertain', 'Command ownership not established')
        run = self._read()
        require(len(canonical(value)) <= run['command_limits']['output_bytes'],
                'output_limit', 'Command ownership exceeds its bound')
        require(value['id'] not in {c['identity']['id'] for c in run['local']['commands']},
                'ownership_uncertain', 'Returned command identity was already registered')
        for process in value['processes']:
            fields(process, ('pid', 'start_id'), 'process identity')
            require(type(process['pid']) is int and process['pid'] > 0 and
                    isinstance(process['start_id'], str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', process['start_id']),
                    'ownership_uncertain', 'Process identity not established')
        return deepcopy(value)

    def _fixture(self, feature):
        from .local_run import verify_prepared
        run = self._read()
        prepared = run['local']['prepared']
        verify_prepared(prepared, run, timeout=self._deadline() - self.monotonic(),
                        max_bytes=run['command_limits']['input_bytes'])
        self.directory = prepared['checkout']
        require(self.adapter is not None, 'configuration_unverified', 'No approved local runtime adapter')
        self._journal('configuration', 'intent', {})
        config = self._call('qualify', directory=self.directory, handoff=prepared['handoff'],
                            runtime=feature['package']['profile']['runtime'], bundle_sha256=run['bundle_sha256'],
                            max_bytes=run['command_limits']['output_bytes'])
        fields(config, ('version', 'api_sha256', 'configuration_sha256', 'bundle_sha256', 'directory',
                        'qualification', 'roles_sha256', 'discovery_sha256', 'permissions_verified',
                        'stopping_verified', 'delegation_verified'), 'configuration gate')
        require(len(canonical(config)) <= run['command_limits']['output_bytes'],
                'output_limit', 'Configuration identity exceeds its bound')
        runtime = feature['package']['profile']['runtime']
        require(config['version'] == runtime['opencode_version'] and
                config['api_sha256'] == runtime['api_sha256'] and
                config['configuration_sha256'] == runtime['configuration_sha256'] and
                config['bundle_sha256'] == run['bundle_sha256'] and config['directory'] == self.directory and
                config['qualification'] in ('deterministic', 'real') and
                all(config[k] is True for k in ('permissions_verified', 'stopping_verified', 'delegation_verified')),
                'configuration_unverified', 'Effective runtime qualification is incomplete')
        hash_value(config['roles_sha256'])
        hash_value(config['discovery_sha256'])
        self._update(lambda r, l: l.update(configuration=deepcopy(config)))
        self._journal('configuration', 'observed', {})
        self._journal('session-create', 'intent', {'directory': self.directory,
                                                  'owner': self.run_key, 'driver_id': self.driver_id})
        session = self._session(self._call('create_session', directory=self.directory,
                                          run_key=self.run_key, driver_id=self.driver_id))
        self._update(lambda r, l: l['sessions'].append(session), stopping=True)
        self._journal('session-create', 'observed', {'id': session['id']})
        self._update(lambda r, l: (r.update(state='local-running'), l.update(last_progress_at=self.clock())))
        profile_commands = feature['package']['profile']['commands']
        commands = [('setup-' + str(i), command) for i, command in enumerate(profile_commands['setup'])]
        commands += sorted(profile_commands['checks'].items())
        for name, command in commands:
            self._children(session)
            command_deadline = min(self._read()['local']['runtime_deadline'], self.clock() + command['timeout_seconds'])
            argv_sha256 = digest(canonical(command['argv']))
            self._journal('command-create', 'intent', {'name': name, 'argv_sha256': argv_sha256,
                                                       'session_id': session['id'], 'directory': self.directory,
                                                       'owner': self.run_key, 'driver_id': self.driver_id,
                                                       'deadline': command_deadline})
            tracked = self._command(self._call('start_command', directory=self.directory, session=session,
                                               argv=list(command['argv']), timeout_seconds=command['timeout_seconds'],
                                               run_key=self.run_key, driver_id=self.driver_id,
                                               seconds=command_deadline - self.clock()), session)
            record = {'identity': tracked, 'name': name, 'argv_sha256': argv_sha256,
                      'deadline': command_deadline, 'status': 'running'}
            self._update(lambda r, l: l['commands'].append(record), stopping=True)
            self._journal('command-create', 'observed', {'id': tracked['id']})
            while True:
                remaining = command_deadline - self.clock()
                require(remaining > 0, 'command_timeout', 'Approved command timed out')
                poll = self._call('poll_command', command=tracked, seconds=min(remaining, run['command_limits']['command_seconds']),
                                  max_bytes=run['command_limits']['output_bytes'])
                fields(poll, ('status', 'exit', 'progress'), 'command observation')
                require(poll['status'] in ('running', 'exited', 'timeout', 'killed') and
                        (poll['exit'] is None or type(poll['exit']) is int) and type(poll['progress']) is bool,
                        'invalid_input', 'Invalid command observation')
                require(self.clock() <= command_deadline, 'command_timeout', 'Late command completion')
                self._update(lambda r, l: l['commands'][-1].update(status=poll['status']))
                if poll['progress']:
                    self._update(lambda r, l: l.update(last_progress_at=self.clock()))
                if poll['status'] == 'running':
                    self.sleep(min(0.05, max(0, command_deadline - self.clock())))
                    continue
                check = {'name': name, 'argv_sha256': record['argv_sha256'], 'exit': poll['exit'],
                         'deadline': command_deadline, 'outcome': 'passed' if poll['status'] == 'exited' and poll['exit'] == 0 else 'failed'}
                self._update(lambda r, l: (l['checks'].append(check), l.update(last_progress_at=self.clock())))
                require(check['outcome'] == 'passed', 'command_failed', 'Approved command failed')
                break
        self._children(session)
        self._finish('fixture-passed')

    def _children(self, session, *, cleanup=False):
        run = self._read()
        values = self._call('discover_children', cleanup=cleanup, session=session, directory=self.directory,
                            run_key=self.run_key, max_bytes=run['command_limits']['output_bytes'])
        require(isinstance(values, list) and len(canonical(values)) <= run['command_limits']['output_bytes'],
                'output_limit', 'Child discovery exceeded bound')
        known = {s['id']: s for s in run['local']['sessions']}
        remaining = list(values)
        while remaining:
            progress = False
            for value in list(remaining):
                if isinstance(value, dict) and value.get('parent_id') in known:
                    child = self._session(value, parent_id=value['parent_id'])
                    require(child['id'] != child['parent_id'], 'ownership_uncertain', 'Cyclic session relationship')
                    if child['id'] in known:
                        require(known[child['id']] == child, 'ownership_uncertain', 'Child identity changed')
                    else:
                        self._update(lambda r, l: l['sessions'].append(child), stopping=cleanup)
                        known[child['id']] = child
                    remaining.remove(value)
                    progress = True
            require(progress, 'ownership_uncertain', 'Unowned child session discovered')

    def _diagnostics(self, values):
        fields(values, ('diagnostics',), 'diagnostic result')
        run = self._read()
        require(isinstance(values['diagnostics'], list) and
                len(canonical(values)) <= run['command_limits']['output_bytes'],
                'output_limit', 'Diagnostic bound exceeded')
        for item in values['diagnostics']:
            fields(item, ('code', 'count'), 'diagnostic')
            require(item['code'] in DIAGNOSTICS and type(item['count']) is int and 0 <= item['count'] <= 2**31,
                    'invalid_input', 'Diagnostics must be non-secret counters')
        self._update(lambda r, l: l['diagnostics'].extend(deepcopy(values['diagnostics'])), stopping=True)

    def _finish(self, outcome):
        run = self._read()
        local = run['local']
        self._update(lambda r, l: r.update(state='local-stopping'), stopping=True)
        sessions, commands = local['sessions'], [v['identity'] for v in local['commands']]
        if self.adapter is not None and (sessions or commands):
            self._journal('collect', 'intent', {}, stopping=True)
            values = self._call('collect', cleanup=True, sessions=sessions, commands=commands,
                                max_bytes=run['command_limits']['output_bytes'])
            self._diagnostics(values)
            self._journal('collect', 'observed', {}, stopping=True)
            self._journal('stop', 'intent', {}, stopping=True)
            stopped = self._call('stop', cleanup=True, directory=self.directory, sessions=sessions, commands=commands,
                                 run_key=self.run_key, driver_id=self.driver_id,
                                 max_bytes=run['command_limits']['output_bytes'])
            fields(stopped, ('confirmed', 'sessions', 'commands', 'descendants_stopped', 'unrelated_preserved'), 'stop result')
            require(stopped['confirmed'] is True and stopped['descendants_stopped'] is True and
                    stopped['unrelated_preserved'] is True and
                    isinstance(stopped['sessions'], list) and isinstance(stopped['commands'], list) and
                    sorted(stopped['sessions']) == sorted(s['id'] for s in sessions) and
                    sorted(stopped['commands']) == sorted(c['id'] for c in commands),
                    'stop_uncertain', 'Owned stopping could not be confirmed')
            self._journal('stop', 'observed', {}, stopping=True)
        self._publish(outcome)

    def _publish(self, outcome):
        run = self._read()
        local = run['local']
        evidence = {'execution': 'trusted-local', 'run_key': self.run_key, 'baseline': run['baseline'],
                    'prepared': local['prepared'], 'configuration': local['configuration'],
                    'sessions': local['sessions'], 'commands': local['commands'], 'checks': local['checks'],
                    'diagnostics': local['diagnostics'], 'outcome': outcome}
        data = canonical(evidence)
        # Input identity manifests can be larger than diagnostic-output allowance;
        # combined evidence remains bounded by both approved allowances.
        require(len(data) <= run['command_limits']['input_bytes'] + run['command_limits']['output_bytes'],
                'output_limit', 'Evidence exceeds its bound')
        sha256 = digest(data)
        if local['prepared']:
            destination = Path(local['artifact']) / 'evidence' / ('result-' + sha256 + '.json')
            self._journal('evidence', 'intent', {'sha256': sha256}, stopping=True)
            with destination.open('xb') as stream:
                stream.write(data + b'\n')
                stream.flush()
                os.fsync(stream.fileno())
            fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            self._journal('evidence', 'observed', {'sha256': sha256}, stopping=True)
        def change(r, l):
            final_outcome = 'held' if l['stop_request'] else outcome
            r['state'] = {'fixture-passed': 'local-fixture-passed', 'failed': 'local-failed', 'held': 'local-held'}[final_outcome]
            r['result'] = {'execution': 'trusted-local', 'outcome': final_outcome,
                           'qualification': l['configuration']['qualification'] if l['configuration'] else None,
                           'evidence_sha256': sha256}
            l['driver'] = None
        self._update(change, stopping=True)

    def _failure(self, exc, *, fixture):
        # No raw exception or output ever reaches the ledger/evidence.
        code = exc.code if isinstance(exc, RoutineError) else 'local_interrupted'
        code = code if code in HOLD_CODES or code == 'command_failed' else 'local_interrupted'
        try:
            self._update(lambda r, l: l.update(hold_reason=code), stopping=True)
        except BaseException:
            pass
        try:
            run = self._read()
            ambiguous = any(v['phase'] == 'intent' and v['effect'] in ('session-create', 'command-create') and
                            not any(w['effect'] == v['effect'] and w['phase'] == 'observed' and
                                    w['sequence'] > v['sequence'] for w in run['local']['checkpoints'])
                            for v in run['local']['checkpoints'])
            stopping_attempted = any(v['effect'] in ('collect', 'stop') and v['phase'] == 'intent'
                                     for v in run['local']['checkpoints'])
            if fixture and not stopping_attempted and self.adapter is not None and (run['local']['sessions'] or run['local']['commands']):
                if not hasattr(self, 'directory'):
                    self.directory = run['local']['prepared']['checkout']
                # Discover known descendants before stopping. Missing ownership is held.
                for session in list(run['local']['sessions']):
                    self._children(session, cleanup=True)
                self._finish('held' if ambiguous or code not in ('command_failed', 'command_timeout') else 'failed')
                return
        except BaseException:
            pass
        try:
            def change(r, l):
                r['state'] = 'local-held'
                r['result'] = {'execution': 'trusted-local', 'outcome': 'held',
                               'qualification': l['configuration']['qualification'] if l['configuration'] else None,
                               'evidence_sha256': None}
                # Retain driver/ownership/checkpoints for W5, never adopt/resume.
            self._update(change, stopping=True)
        except BaseException:
            # Stale drivers cannot overwrite the new owner's ledger.
            pass
