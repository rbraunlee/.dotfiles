"""Fail-closed raw-checkout admission primitives; no mount or recovery authority.

These components require a trusted storage-root descriptor and a privileged xattr
observer. No such administrative binding is installed. Production inspection is
blocked, and no Coordinator operation exposes paths, descriptors or enable flags.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import PurePosixPath
import re
import stat
import time

from .compose import require_quota_backend
from .contracts import RoutineError, canonical, digest, hash_value, identifier, require


DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
CHECKOUT_PARTS = ("home", "worker", "project")


@dataclass(frozen=True)
class StorageBinding:
    # Constructed only by trusted administration, never project profiles/requests.
    root: str
    daemon_id: str

    def __post_init__(self):
        require(isinstance(self.root, str), "invalid_runtime", "Invalid trusted storage root")
        root = PurePosixPath(self.root)
        require(root.is_absolute() and root != PurePosixPath("/") and str(root) == self.root and
                ".." not in root.parts, "invalid_runtime", "Invalid trusted storage root")
        identifier(self.daemon_id)


@dataclass(frozen=True)
class RetainedSource:
    container_id: str
    upper: tuple
    lowers: tuple
    checkpoint_sha256: str
    max_bytes: int

    def __post_init__(self):
        hash_value(self.container_id)
        hash_value(self.checkpoint_sha256)
        require(type(self.max_bytes) is int and self.max_bytes > 0 and isinstance(self.lowers, tuple) and
                1 <= len(self.lowers) <= 128, "invalid_runtime", "Invalid retained source bounds")
        for parts, allow_init in ((self.upper, False), *((parts, True) for parts in self.lowers)):
            require(isinstance(parts, tuple) and len(parts) == 3 and parts[0] == "overlay2" and parts[2] == "diff" and
                    isinstance(parts[1], str) and re.fullmatch(r"[0-9a-f]{64}" + (r"(?:-init)?" if allow_init else ""), parts[1]),
                    "invalid_runtime", "Invalid retained source path")
        require(len(set(self.lowers)) == len(self.lowers) and self.upper not in self.lowers,
                "invalid_runtime", "Aliased retained source layers")


def source_from_inspection(binding, info, value, run):
    """Only durable ownership plus a stopped classic-overlay2 identity may admit."""
    require(isinstance(info, dict) and info.get("ID") == binding.daemon_id and
            info.get("DockerRootDir") == binding.root,
            "invalid_runtime", "Storage daemon differs from the trusted binding")
    require_quota_backend(info)
    require(isinstance(run, dict) and run.get("state") in ("baseline-passed", "sandbox-failed") and
            isinstance(run.get("result"), dict) and run["result"].get("container_stopped") is True,
            "recovery_required", "Only a durably stopped completed baseline may be inspected")
    container_id = hash_value(run.get("container_id"))
    artifact_id = hash_value(run.get("artifact_id"))
    require(isinstance(run.get("runtime_image"), str) and re.fullmatch(r"sha256:[0-9a-f]{64}", run["runtime_image"]),
            "invalid_runtime", "Missing approved retained image identity")
    launch_id = run.get("launch_id")
    require(isinstance(launch_id, str) and re.fullmatch(r"[0-9a-f]{32}", launch_id),
            "recovery_required", "Run lacks a durable preparation identity")
    require(isinstance(value, dict) and isinstance(value.get("Config"), dict) and
            isinstance(value["Config"].get("Labels"), dict) and isinstance(value.get("State"), dict),
            "invalid_runtime", "Malformed retained container inspection")
    labels, state = value["Config"]["Labels"], value["State"]
    require(value.get("Id") == container_id and value.get("Name") == "/routine-" + artifact_id[:32] and
            value.get("Image") == run.get("runtime_image") and
            labels.get("routine.artifact-id") == artifact_id and labels.get("routine.launch-id") == launch_id,
            "recovery_required", "Retained container ownership differs from durable state")
    require(state.get("Running") is False and state.get("Paused") is False and
            state.get("Restarting") is False and state.get("Dead") is False and
            type(state.get("Pid")) is int and state["Pid"] == 0 and state.get("Status") == "exited" and
            all(isinstance(state.get(key), str) and state[key] for key in ("StartedAt", "FinishedAt")),
            "recovery_required", "Source is not a confirmed stopped checkout")
    driver = value.get("GraphDriver")
    require(isinstance(driver, dict) and driver.get("Name") == "overlay2" and isinstance(driver.get("Data"), dict),
            "invalid_runtime", "Retained storage driver is unsupported")
    data = driver["Data"]
    require(data.get("ID") == container_id, "invalid_runtime", "Retained graphdriver identity mismatch")

    def layer_path(path, leaf, allow_init=False):
        require(isinstance(path, str), "invalid_runtime", "Missing storage layer path")
        prefix = re.escape(binding.root) + r"/overlay2/"
        pattern = prefix + r"([0-9a-f]{64}" + (r"(?:-init)?" if allow_init else "") + r")/" + leaf
        matched = re.fullmatch(pattern, path)
        require(matched is not None, "invalid_runtime", "Storage path escapes the trusted layout")
        return ("overlay2", matched.group(1), leaf)

    upper = layer_path(data.get("UpperDir"), "diff")
    require(layer_path(data.get("MergedDir"), "merged")[:2] == upper[:2] and
            layer_path(data.get("WorkDir"), "work")[:2] == upper[:2],
            "invalid_runtime", "Upper/merged/work storage identities differ")
    lower_paths = data.get("LowerDir")
    require(isinstance(lower_paths, str) and 0 < len(lower_paths) <= 65536,
            "invalid_runtime", "Missing or oversized lower-layer identity")
    paths = lower_paths.split(":")
    require(1 <= len(paths) <= 128, "invalid_runtime", "Unsupported lower-layer count")
    lowers = tuple(layer_path(path, "diff", allow_init=True) for path in paths)
    require(len(set(lowers)) == len(lowers) and upper not in lowers,
            "invalid_runtime", "Aliased storage layers cannot establish checkout provenance")
    resources = run.get("resources")
    require(isinstance(resources, dict) and type(resources.get("disk_mb")) is int and resources["disk_mb"] > 0,
            "invalid_runtime", "Missing checkout inspection byte bound")
    require(isinstance(value.get("HostConfig"), dict) and
            value["HostConfig"].get("StorageOpt") == {"size": f"{resources['disk_mb']}M"},
            "invalid_runtime", "Retained writable-layer quota differs from durable state")
    checkpoint = {"container_id": container_id, "image": value["Image"], "labels": labels,
                  "state": state, "driver": driver, "quota": value["HostConfig"]["StorageOpt"]}
    return RetainedSource(container_id, upper, lowers, digest(canonical(checkpoint)), resources["disk_mb"] * 1024**2)


def confirm_source_unchanged(before, after):
    require(before == after, "recovery_required", "Retained source changed during inspection")


def _mount_id(descriptor):
    with open(f"/proc/self/fdinfo/{descriptor}", encoding="ascii") as stream:
        for line in stream:
            if line.startswith("mnt_id:"):
                return int(line.split()[1])
    raise RoutineError("unsafe_storage", "Cannot identify the storage descriptor mount")


def _directory(parent, part, owner_uid=None):
    descriptor = os.open(part, DIRECTORY_FLAGS, dir_fd=parent)
    try:
        info = os.fstat(descriptor)
        require(_mount_id(parent) == _mount_id(descriptor),
                "unsupported_checkout", "Storage ancestry crosses an unapproved mount")
        if owner_uid is not None:
            require(info.st_uid == owner_uid and not stat.S_IMODE(info.st_mode) & 0o022,
                    "unsafe_storage", "Storage ancestry is not controlled by trusted administration")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _walk(parent, parts, checkpoint, owner_uid=None, missing=False):
    descriptor = os.dup(parent)
    try:
        for part in parts:
            checkpoint()
            try:
                child = _directory(descriptor, part, owner_uid)
            except FileNotFoundError:
                if missing:
                    os.close(descriptor)
                    return None
                raise
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _no_overlay_metadata(descriptor, xattrs):
    names = xattrs(descriptor)
    require(isinstance(names, list) and len(names) <= 128 and all(isinstance(name, str) for name in names),
            "unsafe_storage", "Overlay metadata observation is malformed or unbounded")
    require(not any(name.startswith(("trusted.overlay.", "user.overlay.")) for name in names),
            "unsupported_checkout", "Raw checkout depends on unsupported OverlayFS metadata")


@contextmanager
def pin_raw_checkout(storage_fd, source, *, owner_uid, deadline, max_entries=10000, max_depth=64,
                     xattrs=os.listxattr, clock=time.monotonic):
    """Component seam for a future privileged broker. Opens read-only FDs only.

    Caller must hold the routine's source lease, bind storage_fd to trusted
    administration and use a privileged xattr observer. The default production
    entry point below is disabled; ordinary host-user scans are not sufficient.
    """
    require(type(max_entries) is int and max_entries > 0 and type(owner_uid) is int and owner_uid >= 0,
            "invalid_input", "Invalid storage scan bounds")
    require(type(max_depth) is int and 0 <= max_depth <= 64,
            "invalid_input", "Invalid storage nesting bound")
    root = os.fstat(storage_fd)
    require(stat.S_ISDIR(root.st_mode) and root.st_uid == owner_uid and not stat.S_IMODE(root.st_mode) & 0o022,
            "unsafe_storage", "Trusted storage descriptor is unsafe")
    checkout = None

    def checkpoint():
        require(clock() < deadline, "command_timeout", "Retained checkout inspection deadline exhausted")

    def layer(parts):
        descriptor = _walk(storage_fd, parts, checkpoint, owner_uid)
        try:
            _no_overlay_metadata(descriptor, xattrs)
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def project(layer_fd, allow_missing):
        # Check each container-controlled ancestor without following symlinks;
        # OverlayFS redirects/metacopy/opaque state anywhere invalidate raw fidelity.
        descriptor = os.dup(layer_fd)
        try:
            for part in CHECKOUT_PARTS:
                checkpoint()
                try:
                    child = _directory(descriptor, part)
                except FileNotFoundError:
                    if allow_missing:
                        os.close(descriptor)
                        return None
                    raise
                os.close(descriptor)
                descriptor = child
                _no_overlay_metadata(descriptor, xattrs)
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    counts = {"entries": 0, "logical_bytes": 0}

    def scan(descriptor, depth=0):
        checkpoint()
        require(depth <= max_depth, "input_limit", "Retained checkout nesting exceeds its scan bound")
        _no_overlay_metadata(descriptor, xattrs)
        with os.scandir(descriptor) as entries:
            for entry in entries:
                checkpoint()
                counts["entries"] += 1
                require(counts["entries"] <= max_entries, "input_limit", "Retained checkout exceeds its entry bound")
                observed = entry.stat(follow_symlinks=False)
                require(not entry.name.startswith(".wh.") and
                        (stat.S_ISDIR(observed.st_mode) or stat.S_ISREG(observed.st_mode)),
                        "unsupported_checkout", "Raw checkout contains links, whiteouts or special entries")
                flags = DIRECTORY_FLAGS if stat.S_ISDIR(observed.st_mode) else (
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
                child = os.open(entry.name, flags, dir_fd=descriptor)
                try:
                    actual = os.fstat(child)
                    require((actual.st_dev, actual.st_ino, actual.st_mode, actual.st_size) ==
                            (observed.st_dev, observed.st_ino, observed.st_mode, observed.st_size),
                            "unsafe_storage", "Checkout entry changed during inspection")
                    require(actual.st_dev == root.st_dev, "unsupported_checkout", "Checkout crosses a storage mount")
                    require(_mount_id(child) == _mount_id(storage_fd),
                            "unsupported_checkout", "Checkout crosses an unapproved mount")
                    _no_overlay_metadata(child, xattrs)
                    if stat.S_ISDIR(actual.st_mode):
                        scan(child, depth + 1)
                    else:
                        require(actual.st_nlink == 1, "unsupported_checkout", "Checkout hardlinks are unsupported")
                        counts["logical_bytes"] += actual.st_size
                        require(counts["logical_bytes"] <= source.max_bytes,
                                "input_limit", "Retained checkout exceeds its logical-byte bound")
                finally:
                    os.close(child)

    try:
        checkpoint()
        for parts in source.lowers:
            lower = layer(parts)
            try:
                existing = project(lower, True)
                if existing is not None:
                    os.close(existing)
                    raise RoutineError("unsupported_checkout", "Lower-layer checkout content cannot be ignored")
            finally:
                os.close(lower)
        upper = layer(source.upper)
        try:
            checkout = project(upper, False)
        finally:
            os.close(upper)
        require(os.fstat(checkout).st_dev == root.st_dev, "unsupported_checkout", "Checkout crosses a storage mount")
        scan(checkout)
        checkpoint()
        yield checkout, dict(counts)
    except OSError as exc:
        raise RoutineError("unsafe_storage", "Retained storage cannot be safely inspected") from exc
    finally:
        if checkout is not None:
            os.close(checkout)


def production_inspection(*args, **kwargs):
    # Root execution alone is not authorization. No approved privileged broker,
    # pinned-FD Docker mount transport or production policy exists yet.
    raise RoutineError("storage_inspection_unavailable", "Production retained-checkout inspection is not enabled")
