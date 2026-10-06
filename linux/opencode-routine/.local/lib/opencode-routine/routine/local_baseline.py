"""Read a feature ref and immutable objects without loading source Git config."""
import os
from pathlib import Path
import re
import stat
import tempfile
import time

from .contracts import RoutineError, fields, require
from .process import host_environment, run_bounded


def validate_baseline(value):
    fields(value, ("commit", "branch"), "baseline")
    require(isinstance(value["commit"], str) and
            re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value["commit"]),
            "invalid_input", "Baseline must name an exact Git object")
    require(isinstance(value["branch"], str) and
            re.fullmatch(r"refs/heads/features/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", value["branch"]),
            "invalid_input", "Expected an exact feature branch")


def inspect_baseline(project_root, baseline, *, timeout, max_bytes, temporary_root):
    validate_baseline(baseline)
    deadline = time.monotonic() + timeout

    def remaining():
        require(time.monotonic() < deadline, "command_timeout", "Baseline inspection exceeded its deadline")
        return deadline - time.monotonic()

    root = Path(project_root).absolute()
    git_dir = root / ".git"
    objects = git_dir / "objects"
    require(not any(p.is_symlink() for p in (objects, *objects.parents)) and
            git_dir.is_dir() and objects.is_dir(), "unsupported_checkout",
            "Local authorization requires ordinary independent Git metadata")
    require(not (objects / "info").is_symlink(), "unsafe_git", "Linked Git object metadata is forbidden")
    for name in ("alternates", "http-alternates"):
        path = objects / "info" / name
        require(not path.exists() and not path.is_symlink(), "unsafe_git", "Git alternates are forbidden")

    def check_object_storage():
        # Git follows nested loose/packed object paths. Check the whole fixture
        # object tree, not only its root, with bounded metadata and descriptor depth.
        remaining_bytes = max_bytes

        def walk(descriptor, depth):
            nonlocal remaining_bytes
            require(depth <= 64, "unsafe_git", "Git object metadata nesting exceeds its bound")
            with os.scandir(descriptor) as entries:
                for entry in entries:
                    remaining()
                    remaining_bytes -= len(os.fsencode(entry.name)) + 1
                    require(remaining_bytes >= 0, "output_limit", "Git object metadata exceeds its inspection bound")
                    info = entry.stat(follow_symlinks=False)
                    require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode),
                            "unsafe_git", "Git object storage cannot contain links or special files")
                    if stat.S_ISDIR(info.st_mode):
                        child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                        dir_fd=descriptor)
                        try:
                            opened = os.fstat(child)
                            require((info.st_dev, info.st_ino) == (opened.st_dev, opened.st_ino),
                                    "unsafe_git", "Git object directory changed during inspection")
                            walk(child, depth + 1)
                        finally:
                            os.close(child)

        descriptor = os.open(objects, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            walk(descriptor, 0)
        finally:
            os.close(descriptor)

    check_object_storage()

    def read_metadata(path):
        require(not any(p.is_symlink() for p in (path, *path.parents)),
                "unsafe_git", "Linked Git reference metadata is forbidden")
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                    "unsafe_git", "Git reference metadata must be an unlinked regular file")
            data = stream.read(max_bytes + 1)
            after = os.fstat(stream.fileno())
        require(len(data) <= max_bytes, "output_limit", "Git reference metadata exceeds its bound")
        require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                "baseline_moved", "Git reference metadata changed during inspection")
        remaining()
        return data

    def check_ref():
        ref = read_metadata(git_dir / baseline["branch"])
        if ref is None:
            packed = read_metadata(git_dir / "packed-refs") or b""
            matches = [line.split(b" ", 1)[0] for line in packed.splitlines()
                       if line.endswith(b" " + baseline["branch"].encode())]
            require(len(matches) <= 1, "unsafe_git", "Duplicate packed feature reference")
            ref = matches[0] if matches else None
        require(ref is not None, "baseline_missing", "Approved feature reference is missing")
        expected = baseline["commit"].encode()
        require(ref in (expected, expected + b"\n"), "baseline_moved",
                "Feature reference does not match the recorded verified head")

    check_ref()

    # Source config, hooks, grafts, replacement refs and lazy-fetch settings are
    # never consulted. Temporary bare metadata is not a worker checkout.
    with tempfile.TemporaryDirectory(prefix="local-inspect-", dir=temporary_root) as temporary:
        temporary = Path(temporary)
        template = temporary / "empty-template"
        template.mkdir()
        bare = temporary / "bare.git"
        environment = host_environment()
        run_bounded(["/usr/bin/git", "init", "--bare", f"--template={template}",
                     "--object-format=" + ("sha256" if len(baseline["commit"]) == 64 else "sha1"), str(bare)],
                    timeout=remaining(), max_bytes=max_bytes, env=environment, cwd=temporary)
        environment["GIT_OBJECT_DIRECTORY"] = str(objects)
        try:
            object_type = run_bounded(["/usr/bin/git", f"--git-dir={bare}", "--no-replace-objects",
                         "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                         "-c", "protocol.allow=never", "-c", "gc.auto=0", "cat-file", "-t",
                         baseline["commit"]], timeout=remaining(), max_bytes=max_bytes,
                        env=environment, cwd=temporary)
        except RoutineError as exc:
            if exc.code == "adapter_failed":
                raise RoutineError("baseline_missing", "Verified baseline commit is unavailable") from exc
            raise
        require(object_type == b"commit\n", "invalid_baseline", "Verified baseline object must itself be a commit")
        check_object_storage()
        check_ref()
    return dict(baseline)
