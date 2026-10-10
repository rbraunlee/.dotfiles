"""Mirror selectors in native Zsh, with a fully disposable privileged boundary."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ZSHRC = Path(__file__).resolve().parents[3] / 'common/zsh/.zshrc'
TARGET = '/etc/pacman.d/mirrorlist'


class MirrorsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='zsh-mirrors-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.home = self.root / 'home'
        self.home.mkdir()
        self.fixture = self.root / 'functions'
        self.fixture.mkdir()
        (self.fixture / 'compinit').write_text(':\n')
        self.target = self.root / 'mirrorlist'
        self.target.write_text('old list\n')
        self.calls = self.root / 'calls'
        (self.bin / 'tty').write_text('#!/bin/sh\necho /dev/fixture\n')
        (self.bin / 'tty').chmod(0o755)
        self.provider('reflector')
        self.provider('rate-mirrors')
        self.provider('sudo', '''#!/usr/bin/python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ['ROOT']).resolve()
target = '/etc/pacman.d/mirrorlist'
args = sys.argv[1:]
with (root / 'calls').open('a') as log:
    log.write(json.dumps(['sudo', args]) + '\\n')
step = args[0] if args else ''
if os.environ.get('FAIL_STEP') == step:
    sys.exit(19)
def mapped(path):
    if path == target:
        return root / 'mirrorlist'
    if path == target + '.backup':
        return root / 'mirrorlist.backup'
    if path.startswith(target + '.') and path[len(target) + 1:].isalnum():
        return root / ('stage.' + path[len(target) + 1:])
    p = pathlib.Path(path).resolve()
    assert p.parent == root and p.name.startswith('zsh-mirror-candidate.'), path
    return p
if step == 'cp':
    assert args[1:3] == ['-p', '--'] and len(args) == 5
    assert args[3:] == [target, target + '.backup']
    mapped(args[4]).write_bytes(mapped(args[3]).read_bytes())
elif step == 'mktemp':
    assert args == ['mktemp', target + '.XXXXXXXX']
    name = target + '.stage001'
    mapped(name).write_bytes(b'')
    print(name)
elif step == 'install':
    assert args[1:3] == ['-m', '644'] and args[3] == '--' and len(args) == 6
    assert args[5] == target + '.stage001'
    mapped(args[5]).write_bytes(mapped(args[4]).read_bytes())
elif step == 'mv':
    assert args[1:4] == ['-f', '-T', '--'] and args[4:] == [target + '.stage001', target]
    os.replace(mapped(args[4]), mapped(args[5]))
elif step == 'rm':
    assert args[1:3] == ['-f', '--'] and args[3:] == [target + '.stage001']
    mapped(args[3]).unlink(missing_ok=True)
else:
    raise AssertionError(args)
''')
        self.provider('mktemp', '''#!/usr/bin/python3
import os, pathlib, sys
assert len(sys.argv) == 2 and sys.argv[1] == os.environ['ROOT'] + '/zsh-mirror-candidate.XXXXXXXX'
path = pathlib.Path(os.environ['ROOT']) / 'zsh-mirror-candidate.fixture01'
path.write_bytes(b'')
print(path)
''')
        self.provider('rm', '''#!/usr/bin/python3
import os, pathlib, sys
assert sys.argv[1:3] == ['-f', '--'] and len(sys.argv) == 4
path = pathlib.Path(sys.argv[3])
assert path.resolve().parent == pathlib.Path(os.environ['ROOT']).resolve()
assert path.name == 'zsh-mirror-candidate.fixture01'
path.unlink(missing_ok=True)
''')

    def provider(self, name, code=None):
        if code is None:
            code = '''#!/usr/bin/python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
with (pathlib.Path(os.environ['ROOT']) / 'calls').open('a') as log:
    log.write(json.dumps([name, sys.argv[1:]]) + '\\n')
print(os.environ.get('CANDIDATE', 'new list\\n'), end='')
sys.exit(int(os.environ.get('FAIL_GENERATOR', '0')))
'''
        file = self.bin / name
        file.write_text(code)
        file.chmod(0o755)

    def run_shell(self, invocation, *, ostype='linux-gnu', env=None):
        variables = {
            'ROOT': str(self.root), 'HOME': str(self.home), 'ZDOTDIR': str(self.root),
            'XDG_DATA_HOME': str(self.root / 'xdg'), 'XDG_CONFIG_HOME': str(self.root / 'config'),
            'XDG_CACHE_HOME': str(self.root / 'cache'), 'CUDA_HOME': str(self.root / 'absent'),
            'TMPDIR': str(self.root), 'PATH': str(self.bin), 'BIN': str(self.bin),
            'FIXTURE': str(self.fixture), 'ZSHRC': str(ZSHRC),
        }
        variables.update(env or {})
        script = (f'OSTYPE={ostype}\nfpath=( "$FIXTURE" )\nsource "$ZSHRC"\n'
                  'path=( "$BIN" )\n' + invocation + '\n')
        result = subprocess.run(['/usr/bin/zsh', '-f', '-c', script], env=variables,
                                cwd=self.root, capture_output=True, text=True, timeout=10)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        return result, calls

    def test_explicit_mirror_selection_backs_up_before_atomic_publication(self):
        result, calls = self.run_shell('mirror')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_text(), 'new list\n')
        self.assertEqual((self.root / 'mirrorlist.backup').read_text(), 'old list\n')
        self.assertEqual(calls, [
            ['reflector', ['-f', '30', '-l', '30', '--number', '10', '--verbose']],
            ['sudo', ['cp', '-p', '--', TARGET, TARGET + '.backup']],
            ['sudo', ['mktemp', TARGET + '.XXXXXXXX']],
            ['sudo', ['install', '-m', '644', '--', str(self.root / 'zsh-mirror-candidate.fixture01'), TARGET + '.stage001']],
            ['sudo', ['mv', '-f', '-T', '--', TARGET + '.stage001', TARGET]],
        ])

    def test_every_selector_preserves_its_original_selection_intent(self):
        expected = {
            'mirrord': ('reflector', ['--latest', '30', '--number', '10', '--sort', 'delay']),
            'mirrors': ('reflector', ['--latest', '30', '--number', '10', '--sort', 'score']),
            'mirrora': ('reflector', ['--latest', '30', '--number', '10', '--sort', 'age']),
            'mirrorx': ('reflector', ['--age', '6', '--latest', '20', '--fastest', '20', '--threads', '5', '--sort', 'rate', '--protocol', 'https']),
            'mirrorxx': ('reflector', ['--age', '6', '--latest', '20', '--fastest', '20', '--threads', '20', '--sort', 'rate', '--protocol', 'https']),
            'ram': ('rate-mirrors', ['--allow-root', '--disable-comments', 'arch']),
            'rams': ('rate-mirrors', ['--allow-root', '--disable-comments', '--protocol', 'https', 'arch']),
        }
        for selector, (provider, args) in expected.items():
            with self.subTest(selector=selector):
                self.calls.unlink(missing_ok=True)
                self.target.write_text('old list\n')
                result, calls = self.run_shell(selector)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls[0], [provider, args])
                self.assertEqual([call[1][0] for call in calls[1:]], ['cp', 'mktemp', 'install', 'mv'])
                self.assertEqual(self.target.read_text(), 'new list\n')
                self.assertEqual((self.root / 'mirrorlist.backup').read_text(), 'old list\n')

    def test_failed_or_empty_generation_never_reaches_privilege_boundary(self):
        for env in ({'CANDIDATE': ''}, {'FAIL_GENERATOR': '17'}):
            with self.subTest(env=env):
                self.calls.unlink(missing_ok=True)
                result, calls = self.run_shell('rams', env=env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('generator failed or candidate', result.stderr)
                self.assertEqual(calls, [['rate-mirrors', ['--allow-root', '--disable-comments', '--protocol', 'https', 'arch']]])
                self.assertEqual(self.target.read_text(), 'old list\n')
                self.assertFalse((self.root / 'mirrorlist.backup').exists())
                self.assertEqual(list(self.root.glob('zsh-mirror-candidate.*')), [])

    def test_each_privileged_failure_preserves_old_list(self):
        for step, expected in (
            ('cp', ['cp']), ('mktemp', ['cp', 'mktemp']),
            ('install', ['cp', 'mktemp', 'install', 'rm']),
            ('mv', ['cp', 'mktemp', 'install', 'mv', 'rm']),
        ):
            with self.subTest(step=step):
                self.calls.unlink(missing_ok=True)
                (self.root / 'mirrorlist.backup').unlink(missing_ok=True)
                result, calls = self.run_shell('mirrorx', env={'FAIL_STEP': step})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual([call[1][0] for call in calls[1:]], expected)
                self.assertEqual(self.target.read_text(), 'old list\n')
                self.assertEqual(list(self.root.glob('zsh-mirror-candidate.*')), [])
                self.assertEqual(list(self.root.glob('stage.*')), [])
                if step != 'cp':
                    self.assertEqual((self.root / 'mirrorlist.backup').read_text(), 'old list\n')

    def test_missing_providers_arguments_and_startup_are_inert(self):
        result, calls = self.run_shell('source "$ZSHRC"; true')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])
        self.assertEqual(self.target.read_text(), 'old list\n')
        names = 'mirror mirrord mirrors mirrora mirrorx mirrorxx ram rams'
        result, calls = self.run_shell('for name in ' + names + '; do '
                                       '(( $+functions[$name] || $+aliases[$name] )) && exit 30; done; true',
                                       ostype='darwin24')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])
        for invocation in ('mirror extra', 'rams --save /somewhere'):
            result, calls = self.run_shell(invocation)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(calls, [])
        (self.bin / 'reflector').unlink()
        result, calls = self.run_shell('mirror')
        self.assertEqual(result.returncode, 127, result.stderr)
        self.assertIn('reflector', result.stderr)
        self.assertEqual(calls, [])

    def test_invalid_privileged_stage_name_never_reaches_install_or_rename(self):
        self.provider('sudo', '''#!/usr/bin/python3
import json, os, pathlib, sys
args = sys.argv[1:]
assert args[0] in ('cp', 'mktemp')
root = pathlib.Path(os.environ['ROOT'])
with (root / 'calls').open('a') as log:
    log.write(json.dumps(['sudo', args]) + '\\n')
if args[0] == 'cp':
    (root / 'mirrorlist.backup').write_bytes((root / 'mirrorlist').read_bytes())
else:
    print('/etc/pacman.d/unexpected')
''')
        result, calls = self.run_shell('mirror')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unexpected staging path', result.stderr)
        self.assertEqual([call[1][0] for call in calls[1:]], ['cp', 'mktemp'])
        self.assertEqual(self.target.read_text(), 'old list\n')

    def test_missing_sudo_or_local_mktemp_cannot_query_or_change_list(self):
        (self.bin / 'sudo').unlink()
        result, calls = self.run_shell('mirror')
        self.assertEqual(result.returncode, 127, result.stderr)
        self.assertEqual(calls, [])
        self.provider('sudo', '#!/bin/sh\nexit 99\n')
        self.provider('mktemp', '#!/bin/sh\nexit 19\n')
        result, calls = self.run_shell('mirror')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])
        self.assertEqual(self.target.read_text(), 'old list\n')

    def test_failed_cleanup_is_reported_not_mistaken_for_success(self):
        self.provider('rm', '#!/bin/sh\nexit 18\n')
        result, calls = self.run_shell('mirror')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('candidate cleanup failed', result.stderr)
        self.assertEqual(calls[-1][1][0], 'mv')
        self.assertEqual(self.target.read_text(), 'new list\n')
        self.assertEqual((self.root / 'mirrorlist.backup').read_text(), 'old list\n')


if __name__ == '__main__':
    unittest.main()
