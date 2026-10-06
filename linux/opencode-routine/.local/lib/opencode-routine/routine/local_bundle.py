"""Bounded identities and verified copies of a trusted local prompt/skill bundle.

Installation file links are trusted administration inputs, not runtime links.
Snapshots are integrity-checked regular copies; they are not host containment.
Failed destinations are deliberately retained and never adopted on retry.
"""
from contextlib import ExitStack, contextmanager
import hashlib
import math
import os
from pathlib import Path
import stat
import time

from .contracts import RoutineError, canonical, digest, hash_value, relative_path, require


DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


def _budget(max_bytes, timeout):
    require(type(max_bytes) is int and max_bytes > 0,
            "invalid_input", "Bundle byte limit must be a positive integer")
    require(type(timeout) in (int, float) and timeout > 0,
            "invalid_input", "Bundle timeout must be finite and positive")
    try:
        deadline = time.monotonic() + timeout
    except OverflowError as exc:
        raise RoutineError("invalid_input", "Bundle timeout must be finite and positive") from exc
    require(math.isfinite(deadline), "invalid_input", "Bundle timeout must be finite and positive")

    def checkpoint():
        require(time.monotonic() < deadline, "command_timeout", "Local bundle deadline exceeded")

    return checkpoint


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _same_file(first, second):
    require(_stamp(first) == _stamp(second), "changed_input", "Local bundle changed during inspection")


def _same_directory(first, second):
    require(stat.S_ISDIR(second.st_mode) and
            (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino),
            "changed_input", "Bundle directory identity changed")


def _regular(info):
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
            "invalid_input", "Local bundles require regular files without hardlinks")


@contextmanager
def _io_errors():
    try:
        yield
    except FileNotFoundError as exc:
        raise RoutineError("missing_input", "Local bundle input is missing") from exc
    except (OSError, ValueError, RuntimeError, RecursionError) as exc:
        raise RoutineError("invalid_path", "Local bundle paths must be accessible and regular") from exc


@contextmanager
def _directory(path, checkpoint):
    """Pin the absolute directory chain; never follow directory links."""
    path = Path(os.path.abspath(path))
    with ExitStack() as stack:
        descriptor = os.open(path.anchor, DIRECTORY_FLAGS)
        stack.callback(os.close, descriptor)
        chain = []
        for name in path.parts[1:]:
            checkpoint()
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            require(stat.S_ISDIR(info.st_mode), "invalid_path", "Bundle directories cannot be links")
            child = os.open(name, DIRECTORY_FLAGS, dir_fd=descriptor)
            stack.callback(os.close, child)
            # Unrelated sibling activity may change an ancestor's timestamps.
            # Its inode must stay pinned; full tree stamps are checked by _scan.
            _same_directory(info, os.fstat(child))
            chain.append((descriptor, name, info.st_dev, info.st_ino))
            descriptor = child
        yield descriptor, path
        for parent, name, device, inode in chain:
            checkpoint()
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            require(stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == (device, inode),
                    "changed_input", "Bundle directory identity changed")


def _layout(files, directories):
    paths = [record[0] for record in files]
    require({path for path in directories if path and "/" not in path} == {"agents", "skills"},
            "invalid_input", "Bundle root requires dedicated agents and skills directories")
    require("provenance.md" in paths and all(path == "provenance.md" or
            path.startswith(("agents/", "skills/")) for path in paths),
            "invalid_input", "Bundle requires provenance and only agent/skill inputs")
    agents = [path for path in paths if path.startswith("agents/")]
    require(agents and all(len(path.split("/")) == 2 and path.endswith(".md") for path in agents),
            "invalid_input", "Bundle agents must be direct Markdown files")
    skills = {path.split("/")[1] for path in directories if path.startswith("skills/")}
    require(skills and all(f"skills/{skill}/SKILL.md" in paths for skill in skills) and
            all(len(path.split("/")) >= 3 for path in paths if path.startswith("skills/")),
            "invalid_input", "Every selected skill requires its own SKILL.md")


def _capture(root, stack, checkpoint, allow_links):
    """Capture the entire tree before reading, retaining every directory descriptor."""
    files, directories = [], {}

    def walk(descriptor, prefix, depth):
        checkpoint()
        require(depth <= 64, "invalid_input", "Local bundle nesting exceeds the supported limit")
        info = os.fstat(descriptor)
        names = sorted(os.listdir(descriptor))
        require(names, "invalid_input", "Empty bundle directories are forbidden")
        directories[prefix] = (descriptor, info, names)
        for name in names:
            checkpoint()
            path = f"{prefix}/{name}" if prefix else name
            relative_path(path)
            entry = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(entry.st_mode):
                child = os.open(name, DIRECTORY_FLAGS, dir_fd=descriptor)
                stack.callback(os.close, child)
                _same_file(entry, os.fstat(child))
                walk(child, path, depth + 1)
            else:
                linked = stat.S_ISLNK(entry.st_mode)
                require(not linked or allow_links, "invalid_path", "Snapshot links are forbidden")
                target = os.stat(name, dir_fd=descriptor) if linked else entry
                if linked:
                    require(not stat.S_ISDIR(target.st_mode), "invalid_path", "Bundle directory links are forbidden")
                _regular(target)
                files.append((path, descriptor, name, entry, target))

    walk(root, "", 0)
    files.sort(key=lambda record: record[0])
    _layout(files, directories)
    return files, directories


@contextmanager
def _source_file(record, checkpoint):
    path, parent, name, entry, target = record
    with ExitStack() as stack:
        if stat.S_ISLNK(entry.st_mode):
            # /proc anchors relative installation links to the pinned source directory.
            # Resolve only a trusted file link, then open the resolved chain without links.
            linked = os.readlink(name, dir_fd=parent)
            require(linked, "invalid_path", "Empty installation link")
            candidate = Path(linked) if os.path.isabs(linked) else Path(os.readlink(f"/proc/self/fd/{parent}")) / linked
            resolved = candidate.resolve(strict=True)
            directory, _ = stack.enter_context(_directory(resolved.parent, checkpoint))
            descriptor = os.open(resolved.name, FILE_FLAGS, dir_fd=directory)
        else:
            descriptor = os.open(name, FILE_FLAGS, dir_fd=parent)
        stack.callback(os.close, descriptor)
        opened = os.fstat(descriptor)
        _regular(opened)
        _same_file(target, opened)
        _same_file(entry, os.stat(name, dir_fd=parent, follow_symlinks=False))
        yield descriptor
        checkpoint()
        _same_file(opened, os.fstat(descriptor))
        _same_file(target, os.stat(name, dir_fd=parent))


def _copy_directories(destination, directories, stack, checkpoint):
    outputs = {"": destination}
    for path in sorted(path for path in directories if path):
        checkpoint()
        parent, _, name = path.rpartition("/")
        os.mkdir(name, mode=0o700, dir_fd=outputs[parent])
        child = os.open(name, DIRECTORY_FLAGS, dir_fd=outputs[parent])
        stack.callback(os.close, child)
        outputs[path] = child
    return outputs


def _scan(root, max_bytes, checkpoint, *, allow_links, destination=None):
    inventory, remaining = [], max_bytes
    with ExitStack() as stack:
        files, directories = _capture(root, stack, checkpoint, allow_links)
        outputs = _copy_directories(destination, directories, stack, checkpoint) if destination is not None else None
        for record in files:
            checkpoint()
            path, _, name, _, target = record
            require(target.st_size <= remaining, "input_limit", "Local bundle exceeds the byte limit")
            identity, size = hashlib.sha256(), 0
            with _source_file(record, checkpoint) as source, ExitStack() as output_stack:
                output = None
                if outputs is not None:
                    parent = path.rpartition("/")[0]
                    output = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW |
                                     os.O_NONBLOCK | os.O_CLOEXEC, 0o600, dir_fd=outputs[parent])
                    output_stack.callback(os.close, output)
                while True:
                    checkpoint()
                    data = os.read(source, min(65536, remaining - size + 1))
                    checkpoint()
                    if not data:
                        break
                    size += len(data)
                    require(size <= remaining, "input_limit", "Local bundle exceeds the byte limit")
                    identity.update(data)
                    if output is not None:
                        view = memoryview(data)
                        while view:
                            checkpoint()
                            written = os.write(output, view)
                            require(written > 0, "invalid_input", "Bundle copy made no progress")
                            view = view[written:]
                require(size == target.st_size, "changed_input", "Local bundle file size changed")
                if output is not None:
                    os.fchmod(output, 0o400)
                    os.fsync(output)
                    checkpoint()
            remaining -= size
            inventory.append({"path": path, "sha256": identity.hexdigest()})
        for _, parent, name, entry, target in files:
            checkpoint()
            _same_file(entry, os.stat(name, dir_fd=parent, follow_symlinks=False))
            _same_file(target, os.stat(name, dir_fd=parent))
        for descriptor, info, names in directories.values():
            checkpoint()
            _same_file(info, os.fstat(descriptor))
            require(sorted(os.listdir(descriptor)) == names, "changed_input", "Bundle directory contents changed")
        if outputs is not None:
            for descriptor in outputs.values():
                checkpoint()
                os.fsync(descriptor)
        checkpoint()
        return {"sha256": digest(canonical(inventory)), "inventory": inventory}


def describe_bundle(root, *, max_bytes, timeout):
    """Fingerprint all files in a dedicated trusted source bundle."""
    checkpoint = _budget(max_bytes, timeout)
    with _io_errors(), _directory(root, checkpoint) as (source, _):
        checkpoint()
        result = _scan(source, max_bytes, checkpoint, allow_links=True)
    checkpoint()
    return result


def snapshot_bundle(root, destination, expected_sha256, *, max_bytes, timeout):
    """Exclusively create, copy and reread a snapshot; retain every failed copy."""
    hash_value(expected_sha256)
    checkpoint = _budget(max_bytes, timeout)
    with _io_errors(), _directory(root, checkpoint) as (source, source_path):
        destination = Path(os.path.abspath(destination))
        require(not destination.is_relative_to(source_path),
                "invalid_path", "Bundle snapshot must be outside its source")
        with _directory(destination.parent, checkpoint) as (parent, _):
            checkpoint()
            try:
                os.mkdir(destination.name, mode=0o700, dir_fd=parent)
            except FileExistsError as exc:
                raise RoutineError("artifact_exists", "Bundle snapshot destination already exists") from exc
            with ExitStack() as stack:
                output = os.open(destination.name, DIRECTORY_FLAGS, dir_fd=parent)
                stack.callback(os.close, output)
                created = os.fstat(output)
                result = _scan(source, max_bytes, checkpoint, allow_links=True, destination=output)
                require(result["sha256"] == expected_sha256, "changed_input", "Approved local bundle identity mismatch")
                verified = _scan(output, max_bytes, checkpoint, allow_links=False)
                require(verified == result, "changed_input", "Copied local bundle verification failed")
                os.fsync(parent)
                current = os.stat(destination.name, dir_fd=parent, follow_symlinks=False)
                require(stat.S_ISDIR(current.st_mode) and
                        (created.st_dev, created.st_ino) == (current.st_dev, current.st_ino),
                        "changed_input", "Bundle snapshot directory identity changed")
    checkpoint()
    return verified


def verify_snapshot(destination, expected_sha256, *, max_bytes, timeout):
    """Reject changed snapshot bytes, membership, links and nonregular entries."""
    hash_value(expected_sha256)
    checkpoint = _budget(max_bytes, timeout)
    with _io_errors(), _directory(destination, checkpoint) as (source, _):
        checkpoint()
        result = _scan(source, max_bytes, checkpoint, allow_links=False)
        require(result["sha256"] == expected_sha256, "changed_input", "Frozen local bundle identity mismatch")
    checkpoint()
    return result
