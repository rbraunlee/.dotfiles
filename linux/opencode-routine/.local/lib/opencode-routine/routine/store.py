"""One private host ledger, stable flock inodes and crash-safe replacements."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import tempfile

from .contracts import RoutineError, canonical, parse_json, require


class Store:
    def __init__(self, root=None, checkpoint=None):
        if root is None:
            base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
            require(base.is_absolute(), "unsafe_state", "XDG_STATE_HOME must be absolute")
            root = base / "opencode-routine"
        self.root = Path(root).absolute()
        # Do not accept redirected state storage, including symlinked ancestors.
        require(not any(p.is_symlink() for p in (self.root, *self.root.parents)),
                "unsafe_state", "State paths must not contain symlinks")
        self.root = self.root.resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._private(self.root, directory=True)
        self.checkpoint = checkpoint or (lambda _: None)

    @staticmethod
    def _private(path, directory=False):
        info = path.lstat()
        expected = stat.S_ISDIR if directory else stat.S_ISREG
        require(expected(info.st_mode) and info.st_uid == os.geteuid() and
                stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600) and
                (directory or info.st_nlink == 1),
                "unsafe_state", "State must be private, owned by the host user and not linked")

    @contextmanager
    def lock(self, name, blocking=True):
        path = self.root / name
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            self._private(path)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BlockingIOError as exc:
                raise RoutineError("coordinator_busy", "A Coordinator already holds this feature") from exc
            yield
        finally:
            os.close(fd)

    def read(self):
        path = self.root / "ledger.json"
        if not path.exists() and not path.is_symlink():
            return {"version": 1, "features": {}, "runs": {}}
        self._private(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as stream:
            value = parse_json(stream.read())
        require(isinstance(value, dict) and value.get("version") == 1 and
                isinstance(value.get("features"), dict) and isinstance(value.get("runs"), dict),
                "corrupt_state", "Unsupported or malformed ledger; do not reset it")
        return value

    def write(self, value):
        # Callers hold ledger.lock across read-modify-write. Never lock the renamed file.
        fd, temporary = tempfile.mkstemp(prefix=".ledger-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(canonical(value) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            self.checkpoint("before_replace")
            os.replace(temporary, self.root / "ledger.json")
            self.checkpoint("after_replace")
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            self.checkpoint("after_directory_sync")
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
