"""Consumer-scoped broker files; no host credential discovery or secret evidence."""
import os
from pathlib import Path
import stat
import time

from .contracts import RoutineError, canonical, digest, fields, hash_value, identifier, positive, require
from .policy import credential_target
from .proxy import sync_directory
from .store import Store


class CredentialBroker:
    def resolve(self, request, binding, timeout=None):
        # Only a separately approved, bounded development/model broker may replace
        # this implementation. Never discover host auth files or accept raw paths.
        raise RoutineError("policy_unavailable", "Credential broker is not approved or qualified")


class CredentialFiles:
    def __init__(self, root, broker=None, clock=time.time):
        self.root = Path(root)
        self.broker = broker or CredentialBroker()
        self.created = []
        self.clock = clock

    def path(self, binding):
        key = digest(canonical({"ref": binding["ref"], "consumer": binding["consumer"]}))
        return self.root / key

    def stage(self, request, bindings, *, checkpoint, max_bytes):
        hash_value(request["authorization_id"])
        metadata = []
        total = 0
        require(not any(path.is_symlink() for path in (self.root, *self.root.parents)),
                "unsafe_state", "Credential paths cannot contain symlinks")
        if not bindings:
            return metadata
        self.root.mkdir(mode=0o700)
        Store._private(self.root, directory=True)
        try:
            for binding in bindings:
                fields(binding, ("ref", "consumer", "purpose", "max_bytes", "target", "delivery"), "credential delivery")
                identifier(binding["ref"])
                positive(binding["max_bytes"], "credential size limit")
                target = credential_target(binding["ref"], binding["consumer"])
                purpose = "development" if binding["consumer"].startswith("service:") else "model"
                require(binding["purpose"] == purpose and binding["max_bytes"] <= 65536 and
                        binding["target"] == target and binding["delivery"] == "read-only-file",
                        "invalid_profile", "Unapproved credential delivery")
                timeout = checkpoint()
                deadline = None if timeout is None else self.clock() + timeout
                buffer = self.broker.resolve(request, binding, timeout)
                try:
                    checkpoint()
                    require(deadline is None or self.clock() < deadline, "command_timeout", "Credential broker exceeded its deadline")
                    require(isinstance(buffer, bytearray), "invalid_credential", "Broker must return an erasable buffer")
                    total += len(buffer)
                    require(0 < len(buffer) <= binding["max_bytes"] and total <= max_bytes,
                            "input_limit", "Credential staging exceeds the approved byte budget")
                    path = self.path(binding)
                    # Register the inode before writing so partial writes remain
                    # owned cleanup targets; no foreign file is ever overwritten.
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
                    info = os.fstat(fd)
                    self.created.append((path, info.st_dev, info.st_ino))
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(buffer)
                        stream.flush()
                        os.fchmod(stream.fileno(), 0o444)
                        os.fsync(stream.fileno())
                    checkpoint()
                    metadata.append(dict(binding))
                finally:
                    if isinstance(buffer, bytearray):
                        buffer[:] = b"\0" * len(buffer)
            sync_directory(self.root)
            sync_directory(self.root.parent)
            return metadata
        except BaseException:
            self.cleanup()
            raise

    def cleanup(self):
        # Called only for partial staging before dispatch or AFTER confirmed stop.
        # Unlink is not revocation of copies a container/provider already received.
        require(not any(path.is_symlink() for path in (self.root, *self.root.parents)),
                "unsafe_state", "Credential cleanup refuses redirected directories")
        if self.root.exists():
            Store._private(self.root, directory=True)
        while self.created:
            path, device, inode = self.created[-1]
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                    (info.st_dev, info.st_ino) == (device, inode),
                    "unsafe_state", "Credential cleanup refuses changed or linked files")
            path.unlink()
            self.created.pop()
        if self.root.is_dir() and not self.root.is_symlink():
            sync_directory(self.root)
