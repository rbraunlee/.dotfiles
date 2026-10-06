"""Hash-approved regular input files become private, immutable per-run copies."""
import hashlib
import os
from pathlib import Path
import stat
import time

from .contracts import RoutineError, relative_path, require


def snapshot_name(index):
    return f"{index:04d}.bin"


def open_source(root, value):
    """Walk pinned directory descriptors, not previously checked path strings."""
    relative = relative_path(value)
    root = Path(root).absolute()
    directory = os.open(root.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in (*root.parts[1:], *relative.parts[:-1]):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        return os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                       dir_fd=directory)
    except FileNotFoundError as exc:
        raise RoutineError("missing_input", "Approved input file is missing") from exc
    except OSError as exc:
        raise RoutineError("invalid_path", "Input path must not traverse symlinks or non-directories") from exc
    finally:
        os.close(directory)


def read_mount(root, mount, max_bytes, *, destination=None, checkpoint=lambda: None):
    """Bounded streaming hash/copy; never follow symlinks or wait on a FIFO."""
    checkpoint()
    descriptor = open_source(root, mount["source"])
    output = None
    identity, size = hashlib.sha256(), 0
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                "invalid_input", "Input snapshots require regular files without hardlinks")
        require(info.st_size <= max_bytes, "input_limit", "Approved input files exceed the available preparation budget")
        try:
            if destination is not None:
                output = Path(destination).open("xb")
            while True:
                checkpoint()
                data = stream.read(min(65536, max(1, max_bytes - size + 1)))
                if not data:
                    break
                size += len(data)
                require(size <= max_bytes, "input_limit", "Approved input files exceed the available preparation budget")
                identity.update(data)
                if output is not None:
                    output.write(data)
            require(identity.hexdigest() == mount["sha256"], "changed_input", "Approved mount content hash mismatch")
            if output is not None:
                output.flush()
                os.fsync(output.fileno())
        finally:
            if output is not None:
                output.close()
    return {"source": mount["source"], "target": mount["target"], "sha256": identity.hexdigest(), "size_bytes": size}


def describe_mounts(root, mounts, max_bytes, timeout=60):
    deadline = time.monotonic() + timeout

    def checkpoint():
        require(time.monotonic() < deadline, "command_timeout", "Approved input hashing deadline exceeded")

    records, remaining = [], max_bytes
    for mount in mounts:
        record = read_mount(root, mount, remaining, checkpoint=checkpoint)
        records.append(record)
        remaining -= record["size_bytes"]
    return records


def stage_mounts(root, mounts, expected, handoff, max_bytes, checkpoint=lambda: None):
    require(len(mounts) == len(expected), "changed_input", "Approved mount snapshot mapping changed")
    if not mounts:
        return []
    directory = Path(handoff) / "mounts"
    directory.mkdir(mode=0o755)
    records, remaining = [], max_bytes
    for index, (mount, approved) in enumerate(zip(mounts, expected), 1):
        destination = directory / snapshot_name(index)
        record = read_mount(root, mount, remaining, destination=destination, checkpoint=checkpoint)
        require(record == approved, "changed_input", "Input snapshot differs from the authorized package")
        destination.chmod(0o444)
        records.append(record)
        remaining -= record["size_bytes"]
    directory.chmod(0o555)
    return records
