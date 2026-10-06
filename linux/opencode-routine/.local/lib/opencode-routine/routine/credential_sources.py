"""Opt-in trusted file source. No host environment, auth-store discovery or delivery."""
from copy import deepcopy
import math
import os
from pathlib import Path, PurePosixPath
import stat
import time

from .contracts import RoutineError, canonical, fields, hash_value, identifier, require
from .policy import credential_target


def erase(value):
    value[:] = b"\0" * len(value)


def normalized_binding(binding):
    require(isinstance(binding, dict) and set(binding) <= {"ref", "consumer", "purpose", "max_bytes", "target", "delivery"}
            and {"ref", "consumer", "purpose", "max_bytes"} <= set(binding), "invalid_credential", "Unsupported credential binding")
    identifier(binding["ref"])
    target = credential_target(binding["ref"], binding["consumer"])
    purpose = "development" if binding["consumer"].startswith("service:") else "model"
    require(binding["purpose"] == purpose and type(binding["max_bytes"]) is int and 0 < binding["max_bytes"] <= 65536,
            "invalid_credential", "Credential purpose or size bound is invalid")
    require(binding.get("target", target) == target and binding.get("delivery", "read-only-file") == "read-only-file",
            "invalid_credential", "Credential delivery must be the approved scoped file")
    return {key: binding[key] for key in ("ref", "consumer", "purpose", "max_bytes")}


def private_directory(path):
    """Walk absolute ancestry without following links; caller closes returned FD."""
    path = Path(path)
    require(path.is_absolute() and str(path) == os.path.normpath(str(path)), "unsafe_state", "Expected absolute trusted directory")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            require(info.st_uid in (0, os.geteuid()) and
                    (not info.st_mode & 0o022 or info.st_uid == 0 and info.st_mode & stat.S_ISVTX),
                    "unsafe_state", "Unsafe trusted-directory ancestry")
        info = os.fstat(fd)
        require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
                "unsafe_state", "Credential directory must be privately owned")
        return fd
    except BaseException:
        os.close(fd)
        raise


class ScopedFileCredentialBroker:
    """Exact authorization/binding grants supplied by trusted administration only.

    Construction pins directory identity without reading a credential. resolve()
    returns an erasable buffer; the unchanged delivery primitive must erase it.
    Local regular-file reads have before/after deadlines, not a qualified killable
    transport for arbitrary remote filesystems. Nothing installs this by default.
    """
    def __init__(self, root, grants, monotonic=time.monotonic):
        self.root, self.monotonic = Path(root), monotonic
        require(isinstance(grants, list), "invalid_credential", "Expected trusted credential grants")
        self.grants = {}
        for grant in deepcopy(grants):
            fields(grant, ("authorization_id", "binding", "source"), "trusted grant")
            hash_value(grant["authorization_id"])
            binding = normalized_binding(grant["binding"])
            source = grant["source"]
            require(isinstance(source, str) and source and "\0" not in source and "\\" not in source,
                    "invalid_credential", "Expected relative trusted source")
            relative = PurePosixPath(source)
            require(not relative.is_absolute() and str(relative) == source and ".." not in relative.parts,
                    "invalid_credential", "Unsafe trusted source")
            key = (grant["authorization_id"], canonical(binding))
            require(key not in self.grants, "invalid_credential", "Duplicate trusted credential grant")
            self.grants[key] = relative.parts
        try:
            fd = private_directory(self.root)
            try:
                info = os.fstat(fd)
                self.identity = (info.st_dev, info.st_ino)
            finally:
                os.close(fd)
        except OSError:
            raise RoutineError("unsafe_state", "Trusted source directory unavailable") from None

    def resolve(self, request, binding, timeout=None):
        binding = normalized_binding(binding)
        require(isinstance(request, dict), "invalid_credential", "Expected authorized credential request")
        authorization = request.get("authorization_id")
        hash_value(authorization)
        key = (authorization, canonical(binding))
        require(key in self.grants, "invalid_credential", "Credential consumer is not granted by trusted administration")
        # Even a caller omitting a budget gets a finite source-operation budget.
        timeout = 5 if timeout is None else timeout
        require(type(timeout) in (int, float) and math.isfinite(timeout) and timeout > 0,
                "command_timeout", "Credential source deadline exhausted")
        deadline = self.monotonic() + timeout
        def remaining():
            require(self.monotonic() < deadline, "command_timeout", "Credential source exceeded its deadline")
        fd = leaf = None
        value = bytearray()
        scratch = bytearray(min(4096, binding["max_bytes"] + 1))
        success = False
        try:
            remaining()
            fd = private_directory(self.root)
            root = os.fstat(fd)
            require((root.st_dev, root.st_ino) == self.identity, "unsafe_state", "Trusted source directory changed")
            parts = self.grants[key]
            for part in parts[:-1]:
                remaining()
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
                os.close(fd)
                fd = child
                info = os.fstat(fd)
                require(info.st_dev == root.st_dev and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
                        "unsafe_state", "Unsafe credential source directory")
            leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
            before = os.fstat(leaf)
            require(stat.S_ISREG(before.st_mode) and before.st_dev == root.st_dev and before.st_uid == os.geteuid() and
                    before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == 0o600,
                    "unsafe_state", "Expected private regular credential source")
            require(0 < before.st_size <= binding["max_bytes"], "invalid_credential", "Credential source exceeds approved size")
            while len(value) <= binding["max_bytes"]:
                remaining()
                size = min(len(scratch), binding["max_bytes"] + 1 - len(value))
                count = os.readv(leaf, [memoryview(scratch)[:size]])
                value.extend(memoryview(scratch)[:count])
                erase(scratch)
                remaining()
                if not count:
                    break
            after = os.fstat(leaf)
            current = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
            identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode, info.st_nlink, info.st_uid)
            require(identity(before) == identity(after) == identity(current) and len(value) == before.st_size,
                    "unsafe_state", "Credential source changed while reading")
            remaining()
            success = True
            return value
        except OSError:
            raise RoutineError("unsafe_state", "Trusted credential source unavailable") from None
        finally:
            erase(scratch)
            if not success:
                erase(value)
            if leaf is not None:
                os.close(leaf)
            if fd is not None:
                os.close(fd)
