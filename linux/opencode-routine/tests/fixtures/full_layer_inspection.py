"""Read-only qualification probe, not a worker/recovery entry point."""
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


def main():
    commit, branch = sys.argv[1:]
    root = Path('/retained')
    assert Path('/.dockerenv').is_file() and os.geteuid() == 10001
    assert set(os.listdir('/sys/class/net')) == {'lo'}
    assert not Path('/var/run/docker.sock').exists()
    assert os.statvfs(root).f_flag & os.ST_RDONLY
    assert root.is_dir() and not root.is_symlink()
    git_dir = root / '.git'
    assert stat.S_ISDIR(git_dir.lstat().st_mode)
    assert not (git_dir / 'objects/info/alternates').exists()
    assert not (git_dir / 'objects/info/http-alternates').exists()
    entries = 0
    for directory, directories, files in os.walk(git_dir, followlinks=False):
        for name in directories + files:
            mode = (Path(directory) / name).lstat().st_mode
            assert stat.S_ISREG(mode) or stat.S_ISDIR(mode)
            entries += 1
            assert entries <= 10000
    marker = root / 'retained-before-fill'
    assert stat.S_ISREG(marker.lstat().st_mode)
    with marker.open('rb') as stream:
        assert stream.read(128) == b'checkout retained'
    fill = root / 'quota-fill.bin'
    info = fill.lstat()
    assert stat.S_ISREG(info.st_mode) and 0 < info.st_size < 128 * 1024 * 1024
    try:
        descriptor = os.open(root / 'inspection-write-denial', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as error:
        assert error.errno == errno.EROFS
    else:
        os.close(descriptor)
        raise AssertionError('inspection mount permits writes')
    git = ['/usr/bin/git', '--no-replace-objects', '-c', 'core.hooksPath=/dev/null',
           '-c', 'core.fsmonitor=false', '-c', 'safe.directory=/retained', '--git-dir=/retained/.git']
    for ref in ('HEAD', branch):
        result = subprocess.run(git + ['rev-parse', '--verify', ref + '^{commit}'],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5, check=True)
        assert result.stdout.strip() == commit.encode()
    subprocess.run(git + ['fsck', '--full', '--strict', '--no-reflogs'], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=10, check=True)
    print(json.dumps({'version': 1, 'baseline_commit': commit, 'head_and_run_branch_verified': True,
                      'git_metadata_independent': True, 'git_object_connectivity_verified': True,
                      'retained_marker_verified': True, 'fill_file_size_bytes': info.st_size,
                      'mount_read_only': True, 'write_denied_with_erofs': True,
                      'network_loopback_only': True, 'docker_socket_absent': True}, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Private repository bytes, service logs and exception details are not evidence.
        print('{"version":1,"inspection_failed":true}')
        raise SystemExit(1)
