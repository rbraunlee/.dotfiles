"""Independent trusted-local checkout and immutable, complete role handoff.

The caller owns locks, ledger publication, authorization and stopping. Checkpoints
are synchronous fences, not a second state store. Failures retain every artifact;
neither preparation nor verification adopts existing or changed work. Filesystem
deadlines are cooperative, and input bounds are not checkout/resource quotas.
Observed effects follow child-first file/directory fsync; unsupported or failed
sync prevents publication. This is filesystem-backed ordering, not a claim of
hard crash containment or guarantees beyond the filesystem/storage stack.
"""
from contextlib import ExitStack, contextmanager
import hashlib
import math
import os
from pathlib import Path
import stat
import tempfile
import time

from .contracts import (RoutineError, canonical, digest, fields, hash_value,
                        identifier, parse_json, relative_path, require)
from .local_baseline import inspect_baseline, validate_baseline
from .local_bundle import snapshot_bundle, verify_snapshot
from .process import host_environment, run_bounded
from .transfer import export_bundle


DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
PREPARED_FIELDS = ("artifact", "checkout", "branch", "commit", "git_dir", "bundle_sha256", "handoff")


class _Budget:
    def __init__(self, timeout, max_bytes):
        require(type(max_bytes) is int and max_bytes > 0,
                "invalid_input", "Preparation byte bound must be positive")
        require(type(timeout) in (int, float) and timeout > 0,
                "invalid_input", "Preparation deadline must be finite and positive")
        try:
            self.deadline = time.monotonic() + timeout
        except OverflowError as exc:
            raise RoutineError("invalid_input", "Preparation deadline must be finite and positive") from exc
        require(math.isfinite(self.deadline), "invalid_input", "Preparation deadline must be finite and positive")
        self.max_bytes = max_bytes

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, "command_timeout", "Local preparation deadline exceeded")
        return remaining


@contextmanager
def _safe_io():
    try:
        yield
    except RoutineError as exc:
        # Parsers and checkpoints may carry input-derived diagnostics. Preserve
        # the typed error code, never export their raw text through this helper.
        raise RoutineError(exc.code, "Local preparation could not establish the claimed identities") from exc
    except (KeyError, TypeError, AttributeError) as exc:
        raise RoutineError("invalid_input", "Local preparation requires complete validated identities") from exc
    except (OSError, ValueError, RuntimeError, RecursionError) as exc:
        raise RoutineError("invalid_path", "Local preparation paths must be accessible and regular") from exc


def _absolute(path):
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts,
            "invalid_path", "Local preparation requires absolute normalized paths")
    return path


@contextmanager
def _directory(path, budget):
    """Pin each directory component without following links; recheck on return."""
    path = _absolute(path)
    with ExitStack() as stack:
        descriptor = os.open(path.anchor, DIRECTORY_FLAGS)
        stack.callback(os.close, descriptor)
        chain = []
        for name in path.parts[1:]:
            budget.remaining()
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            require(stat.S_ISDIR(info.st_mode), "invalid_path", "Linked preparation directories are forbidden")
            child = os.open(name, DIRECTORY_FLAGS, dir_fd=descriptor)
            stack.callback(os.close, child)
            require(_inode(info) == _inode(os.fstat(child)), "changed_input", "Preparation directory changed")
            chain.append((descriptor, name, _inode(info)))
            descriptor = child
        yield descriptor
        for parent, name, identity in chain:
            budget.remaining()
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            require(stat.S_ISDIR(info.st_mode) and _inode(info) == identity,
                    "changed_input", "Preparation directory changed")


def _inode(info):
    return {"device": info.st_dev, "inode": info.st_ino}


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _file(parent, name, limit, budget, *, contents=False):
    budget.remaining()
    before = os.stat(name, dir_fd=parent, follow_symlinks=False)
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
            "invalid_path", "Preparation files cannot be links or special files")
    require(before.st_size <= limit, "input_limit", "Combined preparation inputs exceed the byte bound")
    descriptor = os.open(name, FILE_FLAGS, dir_fd=parent)
    with os.fdopen(descriptor, "rb") as stream:
        require(_stamp(before) == _stamp(os.fstat(stream.fileno())), "changed_input", "Preparation input changed")
        identity, chunks, size = hashlib.sha256(), [], 0
        while True:
            budget.remaining()
            data = stream.read(min(65536, limit - size + 1))
            budget.remaining()
            if not data:
                break
            size += len(data)
            require(size <= limit, "input_limit", "Combined preparation inputs exceed the byte bound")
            identity.update(data)
            if contents:
                chunks.append(data)
        require(_stamp(before) == _stamp(os.fstat(stream.fileno())) and
                _stamp(before) == _stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)),
                "changed_input", "Preparation input changed")
    return (b"".join(chunks) if contents else identity.hexdigest()), size


def _read(root, name, budget, limit=None):
    relative_path(name)
    path = root / name
    with _directory(path.parent, budget) as parent:
        return _file(parent, path.name, budget.max_bytes if limit is None else limit, budget, contents=True)[0]


def _inventory(root, limit, budget):
    inventory, size = [], 0

    def walk(descriptor, prefix, depth):
        nonlocal size
        budget.remaining()
        require(depth <= 64, "invalid_path", "Handoff nesting exceeds its bound")
        before = os.fstat(descriptor)
        names = sorted(os.listdir(descriptor))
        require(names, "changed_input", "Empty handoff directories are forbidden")
        for name in names:
            budget.remaining()
            path = f"{prefix}/{name}" if prefix else name
            relative_path(path)
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, DIRECTORY_FLAGS, dir_fd=descriptor)
                try:
                    require(_stamp(info) == _stamp(os.fstat(child)), "changed_input", "Handoff directory changed")
                    walk(child, path, depth + 1)
                    require(_stamp(info) == _stamp(os.stat(name, dir_fd=descriptor, follow_symlinks=False)),
                            "changed_input", "Handoff directory changed")
                finally:
                    os.close(child)
            else:
                identity, count = _file(descriptor, name, limit - size, budget)
                size += count
                inventory.append({"path": path, "sha256": identity})
        require(_stamp(before) == _stamp(os.fstat(descriptor)) and sorted(os.listdir(descriptor)) == names,
                "changed_input", "Handoff membership changed")

    with _directory(root, budget) as descriptor:
        walk(descriptor, "", 0)
    inventory.sort(key=lambda entry: entry["path"])
    return {"path": str(root), "sha256": digest(canonical(inventory)), "inventory": inventory}, size


def _write(root, name, data, budget, *, available):
    require(len(data) <= available, "input_limit", "Combined preparation inputs exceed the byte bound")
    relative_path(name)
    path = root / name
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with _directory(path.parent, budget) as parent:
        descriptor = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=parent)
        with os.fdopen(descriptor, "wb") as stream:
            budget.remaining()
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), 0o400)
            os.fsync(stream.fileno())
            budget.remaining()


def _sync(descriptor, budget):
    budget.remaining()
    os.fsync(descriptor)
    budget.remaining()


def _sync_tree(root, budget):
    """Flush owned files, then directories child-first, without following links.

    Git may create application symlinks; syncing their containing directory
    persists their entries without touching the target. Metadata and handoff
    links remain forbidden by the existing verification gates. This bounded
    metadata traversal is not a disk/content quota on the application checkout.
    """
    metadata_bytes = budget.max_bytes

    def walk(descriptor, depth):
        nonlocal metadata_bytes
        budget.remaining()
        require(depth <= 64, "invalid_path", "Artifact sync nesting exceeds its bound")
        before = os.fstat(descriptor)
        names = sorted(os.listdir(descriptor))
        for name in names:
            budget.remaining()
            metadata_bytes -= len(os.fsencode(name)) + 1
            require(metadata_bytes >= 0, "output_limit", "Artifact sync metadata exceeds its inspection bound")
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                continue
            directory = stat.S_ISDIR(info.st_mode)
            require(directory or stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                    "invalid_path", "Artifact sync requires independent regular files")
            child = os.open(name, DIRECTORY_FLAGS if directory else FILE_FLAGS, dir_fd=descriptor)
            try:
                require(_stamp(info) == _stamp(os.fstat(child)), "changed_input", "Artifact changed before sync")
                if directory:
                    walk(child, depth + 1)
                else:
                    _sync(child, budget)
                require(_stamp(info) == _stamp(os.fstat(child)) and
                        _stamp(info) == _stamp(os.stat(name, dir_fd=descriptor, follow_symlinks=False)),
                        "changed_input", "Artifact changed during sync")
            finally:
                os.close(child)
        require(_stamp(before) == _stamp(os.fstat(descriptor)) and sorted(os.listdir(descriptor)) == names,
                "changed_input", "Artifact membership changed during sync")
        _sync(descriptor, budget)

    with _directory(root, budget) as descriptor:
        walk(descriptor, 0)


def _run_identity(run):
    require(run.get("schema_version") == 1 and run.get("execution") == "trusted-local" and
            run["request"].get("execution") == "trusted-local",
            "execution_mismatch", "Preparation requires an explicit local claim")
    request = run["request"]
    for key in ("project_id", "feature_id", "slice_id", "run_id"):
        identifier(request[key])
    validate_baseline(run["baseline"])
    require(request["baseline"] == run["baseline"], "identity_conflict", "Claim baseline identity differs")
    for key in ("bundle_sha256", "profile_sha256", "spec_sha256", "ticket_sha256"):
        hash_value(run[key])
    require(run["bundle_snapshot"]["sha256"] == run["bundle_sha256"],
            "identity_conflict", "Claim bundle identity differs")
    return "routine/{feature_id}/{slice_id}/{run_id}".format(**request)


def _package(package, run):
    """Reconcile all exact snapshots, not just the selected slice summary."""
    manifest, profile, snapshots = package["manifest"], package["profile"], package["snapshots"]
    require(manifest["feature_id"] == run["request"]["feature_id"] and
            manifest.get("execution") == profile.get("execution") == "trusted-local" and
            manifest.get("version") == 2 and profile.get("version") == 4,
            "identity_conflict", "Planning execution identity differs")
    approval = f".opencode/routine/features/{manifest['feature_id']}/approval.json"
    profile_path = ".opencode/routine/project.json"
    entries = [manifest["spec"], *manifest["tickets"]]
    expected = {approval, profile_path, *(entry["path"] for entry in entries)}
    require(set(snapshots) == expected, "changed_input", "Full planning package membership differs")
    for name, text in snapshots.items():
        relative_path(name)
        require(isinstance(text, str), "invalid_input", "Planning snapshots must contain exact UTF-8 text")
    require(parse_json(snapshots[approval]) == manifest and parse_json(snapshots[profile_path]) == profile,
            "changed_input", "Planning metadata differs from its exact snapshot")
    require(digest(snapshots[profile_path].encode()) == manifest["profile_sha256"] == run["profile_sha256"],
            "changed_input", "Planning profile identity differs")
    for entry in entries:
        require(digest(snapshots[entry["path"]].encode()) == entry["sha256"],
                "changed_input", "Planning document identity differs")
    selected = [entry for entry in manifest["tickets"] if entry["slice_id"] == run["request"]["slice_id"]]
    require(len(selected) == 1 and selected[0]["sha256"] == run["ticket_sha256"] and
            selected[0]["criteria"] == run["criteria"] and manifest["spec"]["sha256"] == run["spec_sha256"] and
            manifest["bundle_sha256"] == run["bundle_sha256"] and
            all(profile[key] == run[key] for key in ("budgets", "command_limits", "credential_refs")),
            "identity_conflict", "Claim differs from the approved planning package")
    return selected[0]


def _context(run, planning, paths, filesystem, export_sha256):
    return {"version": 1, "execution": "trusted-local", "request": run["request"],
            "baseline": run["baseline"], "criteria": run["criteria"],
            **{key: run[key] for key in ("bundle_sha256", "profile_sha256", "spec_sha256", "ticket_sha256",
                                        "budgets", "command_limits", "credential_refs")},
            "bundle_inventory": run["bundle_snapshot"]["inventory"], "planning": planning,
            "paths": paths, "filesystem": filesystem, "export_sha256": export_sha256}


def _readme(manifest, ticket, run):
    return ("# Exact authorized slice handoff\n\n"
            "Trusted local execution; this checkout is not host security containment.\n"
            "These immutable inputs are not an operational status ledger.\n\n"
            f"- Full feature spec: planning/{manifest['spec']['path']}\n"
            f"- Selected ticket: planning/{ticket['path']}\n"
            f"- Approval: planning/.opencode/routine/features/{manifest['feature_id']}/approval.json\n"
            "- Approved profile: planning/.opencode/routine/project.json\n"
            "- Full frozen agents, skills and resources: bundle/\n"
            "- Exact run identity, baseline, limits and applicable criteria: context.json\n"
            f"- Applicable criteria: {', '.join(run['criteria'])}\n\n"
            "All approved tickets are included at their original paths below planning/.\n"
            "Read the full spec and selected ticket, not only this index.\n").encode()


def _git(argv, cwd, budget, environment=None):
    result = run_bounded(["/usr/bin/git", "--no-replace-objects", "-c", "core.hooksPath=/dev/null",
                          "-c", "core.fsmonitor=false", "-c", "protocol.allow=never", "-c", "gc.auto=0",
                          *argv], timeout=budget.remaining(), max_bytes=budget.max_bytes,
                         env=environment or host_environment(), cwd=cwd)
    budget.remaining()
    return result


def _checkout(prepared, run, budget):
    checkout, git_dir = Path(prepared["checkout"]), Path(prepared["git_dir"])
    # Scan all metadata: not merely the object root. No links, shared files,
    # alternates, commondir, worktree routing, grafts or replacement objects.
    metadata_bytes = budget.max_bytes

    def walk(descriptor, depth):
        nonlocal metadata_bytes
        require(depth <= 64, "unsafe_git", "Git metadata nesting exceeds its bound")
        for name in os.listdir(descriptor):
            budget.remaining()
            metadata_bytes -= len(os.fsencode(name)) + 1
            require(metadata_bytes >= 0, "output_limit", "Git metadata exceeds its inspection bound")
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                    "unsafe_git", "Git metadata cannot contain links or shared files")
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, DIRECTORY_FLAGS, dir_fd=descriptor)
                try:
                    require(_inode(info) == _inode(os.fstat(child)), "unsafe_git", "Git metadata changed")
                    walk(child, depth + 1)
                finally:
                    os.close(child)

    with _directory(checkout, budget), _directory(git_dir, budget) as descriptor:
        walk(descriptor, 0)
        for name in ("commondir", "gitdir", "worktrees", "objects/info/alternates",
                     "objects/info/http-alternates", "info/grafts", "refs/replace"):
            path = git_dir / name
            require(not path.exists() and not path.is_symlink(), "unsafe_git", "Shared or replaced Git metadata is forbidden")
        require(_read(git_dir, "HEAD", budget) == f"ref: refs/heads/{prepared['branch']}\n".encode() and
                _read(git_dir, f"refs/heads/{prepared['branch']}", budget) == (prepared["commit"] + "\n").encode(),
                "baseline_moved", "Prepared branch or HEAD differs from the claimed baseline")
    # Never execute Git with the checkout's mutable config. Inspect exact objects
    # through a disposable bare view with no source hooks/config/replacements.
    with tempfile.TemporaryDirectory(prefix="verify-", dir=Path(prepared["artifact"]) / "evidence") as temporary:
        temporary = Path(temporary)
        template = temporary / "empty-template"
        template.mkdir()
        bare = temporary / "bare.git"
        _git(["init", "--bare", f"--template={template}",
              "--object-format=" + ("sha256" if len(prepared["commit"]) == 64 else "sha1"), str(bare)], temporary, budget)
        environment = host_environment()
        environment["GIT_OBJECT_DIRECTORY"] = str(git_dir / "objects")
        result = _git([f"--git-dir={bare}", "cat-file", "-t", prepared["commit"]], temporary, budget, environment)
        require(result == b"commit\n", "invalid_baseline", "Prepared baseline must be an exact commit")
        _git([f"--git-dir={bare}", "rev-list", "--objects", "--missing=error", prepared["commit"]],
             temporary, budget, environment)


def _verify(prepared, run, budget):
    fields(prepared, PREPARED_FIELDS, "prepared clone")
    branch = _run_identity(run)
    artifact = _absolute(prepared["artifact"])
    require(prepared["checkout"] == str(artifact / "checkout") and
            prepared["git_dir"] == str(artifact / "checkout/.git") and
            prepared["handoff"]["path"] == str(artifact / "handoff") and
            prepared["branch"] == branch and prepared["commit"] == run["baseline"]["commit"] and
            prepared["bundle_sha256"] == run["bundle_sha256"],
            "identity_conflict", "Prepared paths or run identity differ")
    fields(prepared["handoff"], ("path", "sha256", "inventory"), "handoff")
    handoff = artifact / "handoff"
    with _directory(artifact, budget) as descriptor:
        export_sha256, export_size = _file(descriptor, "source.bundle", budget.max_bytes, budget)
    observed, _ = _inventory(handoff, budget.max_bytes - export_size, budget)
    require(observed == prepared["handoff"], "changed_input", "Prepared handoff inventory differs")
    context = parse_json(_read(handoff, "context.json", budget))
    filesystem = {}
    for name in ("artifact", "checkout", "git_dir"):
        with _directory(Path(prepared[name]), budget) as descriptor:
            filesystem[name] = _inode(os.fstat(descriptor))
    planning = context["planning"]
    require(context == _context(run, planning, context["paths"], filesystem, export_sha256),
            "changed_input", "Prepared context or filesystem identity differs")
    snapshots = {entry["path"]: _read(handoff / "planning", entry["path"], budget).decode()
                 for entry in planning}
    approval = f".opencode/routine/features/{run['request']['feature_id']}/approval.json"
    manifest = parse_json(snapshots[approval])
    profile = parse_json(snapshots[".opencode/routine/project.json"])
    ticket = _package({"manifest": manifest, "profile": profile, "snapshots": snapshots}, run)
    require(planning == [{"path": name, "sha256": digest(text.encode())} for name, text in sorted(snapshots.items())],
            "changed_input", "Planning inventory differs")
    require(context["paths"] == {"spec": "planning/" + manifest["spec"]["path"],
                                  "ticket": "planning/" + ticket["path"], "bundle": "bundle/"} and
            _read(handoff, "README.md", budget) == _readme(manifest, ticket, run),
            "changed_input", "Readable handoff context differs")
    frozen = verify_snapshot(handoff / "bundle", run["bundle_sha256"],
                             max_bytes=budget.max_bytes - export_size, timeout=budget.remaining())
    budget.remaining()
    require(frozen["inventory"] == run["bundle_snapshot"]["inventory"],
            "changed_input", "Prepared frozen bundle inventory differs")
    expected = {"context.json", "README.md", *("planning/" + name for name in snapshots),
                *("bundle/" + entry["path"] for entry in frozen["inventory"])}
    require({entry["path"] for entry in observed["inventory"]} == expected,
            "changed_input", "Prepared handoff is incomplete")
    _checkout(prepared, run, budget)
    budget.remaining()
    return prepared


def prepare_clone(feature, run, destination, *, timeout, max_bytes, checkpoint):
    """Exclusively create a clone/handoff; the synchronous owner fences all effects."""
    budget = _Budget(timeout, max_bytes)
    with _safe_io():
        branch = _run_identity(run)
        require(feature.get("schema_version") == 1 and feature.get("execution") == "trusted-local",
                "execution_mismatch", "Preparation requires local feature authorization")
        require(feature["authorization_id"] == run["request"]["authorization_id"] and
                feature["verified_head"] == run["baseline"] and feature["bundle_snapshot"] == run["bundle_snapshot"],
                "identity_conflict", "Feature and claim identity differ")
        package = feature["package"]
        ticket = _package(package, run)
        root, artifact = _absolute(feature["project_root"]), _absolute(destination)
        frozen = _absolute(feature["bundle_snapshot"]["path"])
        require(not artifact.is_relative_to(root) and not root.is_relative_to(artifact) and
                not artifact.is_relative_to(frozen) and not frozen.is_relative_to(artifact),
                "invalid_path", "Artifacts must be distinct from source inputs")
        require(callable(checkpoint), "invalid_input", "Preparation requires an owner checkpoint")
        artifact_identity = None

        def sync_artifact():
            with _directory(artifact, budget) as descriptor:
                require(_inode(os.fstat(descriptor)) == artifact_identity,
                        "changed_input", "Artifact directory identity changed before publication")
            _sync_tree(artifact, budget)
            # Persist the artifact root's own name only after syncing its inode
            # and descendants; all other new names are covered by _sync_tree.
            with _directory(artifact.parent, budget) as parent:
                _sync(parent, budget)

        def fence(name, phase, identity):
            budget.remaining()
            if phase == "observed":
                sync_artifact()
            checkpoint(name, {"phase": phase, "identity": identity})
            budget.remaining()
            if artifact_identity is not None:
                with _directory(artifact, budget) as descriptor:
                    require(_inode(os.fstat(descriptor)) == artifact_identity,
                            "changed_input", "Artifact directory identity changed at an owner fence")

        fence("artifact", "intent", {"artifact": str(artifact)})
        with _directory(artifact.parent, budget) as parent:
            try:
                os.mkdir(artifact.name, mode=0o700, dir_fd=parent)
            except FileExistsError as exc:
                raise RoutineError("artifact_exists", "Local run artifact destination already exists") from exc
            with _directory(artifact, budget) as descriptor:
                artifact_identity = _inode(os.fstat(descriptor))
        fence("artifact", "observed", {"artifact": str(artifact), **artifact_identity})
        (artifact / "evidence").mkdir(mode=0o700)
        template = artifact / "empty-template"
        template.mkdir(mode=0o700)

        def check_inputs():
            total = 0
            for name, text in package["snapshots"].items():
                data = text.encode()
                total += len(data)
                require(total <= max_bytes, "input_limit", "Combined preparation inputs exceed the byte bound")
                require(_read(root, name, budget) == data, "changed_input", "Authorized planning bytes changed")
            result = verify_snapshot(frozen, run["bundle_sha256"], max_bytes=max_bytes - total,
                                     timeout=budget.remaining())
            budget.remaining()
            require(result["inventory"] == feature["bundle_snapshot"]["inventory"],
                    "changed_input", "Authorized bundle inventory changed")
            _, bundle_size = _inventory(frozen, max_bytes - total, budget)
            total += bundle_size
            inspect_baseline(root, run["baseline"], timeout=budget.remaining(), max_bytes=max_bytes,
                             temporary_root=artifact / "evidence")
            budget.remaining()
            return total

        input_size = check_inputs()
        export = artifact / "source.bundle"
        fence("export", "intent", {"path": str(export), "commit": run["baseline"]["commit"]})
        require(max_bytes > input_size, "input_limit", "Combined preparation inputs exceed the byte bound")
        export_sha256 = export_bundle(root, run["baseline"]["commit"], export,
                                     timeout=budget.remaining(), max_bytes=max_bytes - input_size)
        budget.remaining()
        with _directory(artifact, budget) as descriptor:
            observed_hash, export_size = _file(descriptor, "source.bundle", max_bytes - input_size, budget)
        require(observed_hash == export_sha256, "changed_input", "Exported bundle identity changed")
        fence("export", "observed", {"path": str(export), "sha256": export_sha256, "bytes": export_size})
        checkout = artifact / "checkout"
        prepared = {"artifact": str(artifact), "checkout": str(checkout), "branch": branch,
                    "commit": run["baseline"]["commit"], "git_dir": str(checkout / ".git"),
                    "bundle_sha256": run["bundle_sha256"]}
        fence("clone", "intent", dict(prepared))
        require(not checkout.exists() and not checkout.is_symlink(), "artifact_exists", "Checkout destination already exists")
        with _directory(template, budget) as descriptor:
            require(not os.listdir(descriptor), "unsafe_git", "Clone requires a fresh empty Git template")
        _git(["-c", "protocol.file.allow=always", "clone", "--no-local", "--no-hardlinks", "--no-checkout",
              f"--template={template}", "--branch=routine-source", str(export), str(checkout)], artifact, budget)
        _git([f"--git-dir={checkout / '.git'}", f"--work-tree={checkout}", "checkout", "--no-recurse-submodules",
              "-b", branch, prepared["commit"]], artifact, budget)
        _checkout(prepared, run, budget)
        fence("clone", "observed", dict(prepared))
        check_inputs()
        handoff = artifact / "handoff"
        fence("handoff", "intent", {"path": str(handoff), "bundle_sha256": run["bundle_sha256"]})
        handoff.mkdir(mode=0o700)
        available = max_bytes - export_size
        for name, text in sorted(package["snapshots"].items()):
            data = text.encode()
            _write(handoff, "planning/" + name, data, budget, available=available)
            available -= len(data)
        copied = snapshot_bundle(frozen, handoff / "bundle", run["bundle_sha256"],
                                 max_bytes=available, timeout=budget.remaining())
        budget.remaining()
        require(copied["inventory"] == feature["bundle_snapshot"]["inventory"],
                "changed_input", "Copied feature bundle inventory differs")
        _, copied_size = _inventory(handoff / "bundle", available, budget)
        available -= copied_size
        filesystem = {}
        for name in ("artifact", "checkout", "git_dir"):
            with _directory(Path(prepared[name]), budget) as descriptor:
                filesystem[name] = _inode(os.fstat(descriptor))
        require(filesystem["artifact"] == artifact_identity, "changed_input", "Artifact directory changed")
        planning = [{"path": name, "sha256": digest(text.encode())} for name, text in sorted(package["snapshots"].items())]
        paths = {"spec": "planning/" + package["manifest"]["spec"]["path"],
                 "ticket": "planning/" + ticket["path"], "bundle": "bundle/"}
        context_data = canonical(_context(run, planning, paths, filesystem, export_sha256))
        _write(handoff, "context.json", context_data, budget, available=available)
        available -= len(context_data)
        _write(handoff, "README.md", _readme(package["manifest"], ticket, run), budget, available=available)
        prepared["handoff"], _ = _inventory(handoff, max_bytes - export_size, budget)
        _verify(prepared, run, budget)
        check_inputs()
        fence("handoff", "observed", dict(prepared["handoff"]))
        # An owner checkpoint may take time or observe concurrent input mutation.
        # Recheck after the last fence; never publish a late or altered result.
        _verify(prepared, run, budget)
        # Verification creates/removes disposable evidence metadata. Sync the
        # final owned tree again before returning it for durable ledger publication.
        sync_artifact()
        return prepared


def verify_prepared(prepared, run, *, timeout, max_bytes):
    """Recheck exact identities without consulting mutable source Git config."""
    budget = _Budget(timeout, max_bytes)
    with _safe_io():
        return _verify(prepared, run, budget)
