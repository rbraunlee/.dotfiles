"""Export a commit without loading any source repository Git configuration."""
import os
from pathlib import Path
import tempfile
import time

from .contracts import require
from .process import host_environment, run_bounded


def export_bundle(project_root, commit, destination, *, timeout, max_bytes):
    deadline = time.monotonic() + timeout

    def remaining():
        require(deadline > time.monotonic(), "command_timeout", "Git export budget exhausted")
        return deadline - time.monotonic()

    root = Path(project_root)
    git_dir = root / ".git"
    objects = git_dir / "objects"
    require(git_dir.is_dir() and not git_dir.is_symlink() and objects.is_dir() and not objects.is_symlink(),
            "unsupported_checkout", "M2 export requires an ordinary checkout with independent Git objects")
    require(not (objects / "info").is_symlink(), "unsafe_git", "Symlinked object metadata is forbidden")
    for name in ("alternates", "http-alternates"):
        require(not (objects / "info" / name).exists() and not (objects / "info" / name).is_symlink(),
                "unsafe_git", "Source Git alternates are forbidden")
    # A fresh bare Git directory ignores source config, refs, hooks, grafts and
    # replacement refs. Only immutable objects are read from the source.
    with tempfile.TemporaryDirectory(prefix="export-", dir=Path(destination).parent) as temporary:
        temporary = Path(temporary)
        template = temporary / "empty-template"
        template.mkdir()
        bare = temporary / "bare.git"
        environment = host_environment()
        environment["GIT_DIR"] = str(bare)
        run_bounded(["/usr/bin/git", "init", "--bare", f"--template={template}",
                     "--object-format=" + ("sha256" if len(commit) == 64 else "sha1"), str(bare)],
                    timeout=remaining(), env=environment, cwd=temporary)
        environment["GIT_OBJECT_DIRECTORY"] = str(objects)
        command = ["/usr/bin/git", f"--git-dir={bare}", "-c", "core.hooksPath=/dev/null",
                   "-c", "core.fsmonitor=false", "-c", "protocol.allow=never", "-c", "gc.auto=0"]
        run_bounded(command + ["cat-file", "-e", commit + "^{commit}"], timeout=remaining(), env=environment, cwd=temporary)
        run_bounded(command + ["update-ref", "refs/heads/routine-source", commit], timeout=remaining(), env=environment, cwd=temporary)
        # Any partial file is retained as diagnostics, never launched.
        with Path(destination).open("xb") as stream:
            run_bounded(command + ["bundle", "create", "-", "refs/heads/routine-source"],
                        timeout=remaining(), max_bytes=max_bytes, env=environment, output=stream, cwd=temporary)
            stream.flush()
            os.fsync(stream.fileno())
    # Bundle bytes are bounded by the approved disk limit, not kept in memory.
    import hashlib
    identity = hashlib.sha256()
    with Path(destination).open("rb") as stream:
        while data := stream.read(65536):
            identity.update(data)
    return identity.hexdigest()
