"""Injected inspection contracts, not an executable Docker/mount implementation."""
from dataclasses import dataclass
import math
import os
from pathlib import PurePosixPath
from typing import ContextManager, Protocol

from .contracts import RoutineError, canonical, digest, hash_value, identifier, require
from .retention import _mount_id


@dataclass(frozen=True)
class InspectionRequest:
    project_id: str
    feature_id: str
    run_id: str

    def __post_init__(self):
        for value in (self.project_id, self.feature_id, self.run_id):
            identifier(value)

    def as_dict(self):
        return {"project_id": self.project_id, "feature_id": self.feature_id, "run_id": self.run_id}


@dataclass(frozen=True)
class InspectionLimits:
    total_seconds: float = 60
    stop_seconds: float = 20
    command_seconds: float = 15
    max_entries: int = 10000
    max_depth: int = 64
    max_evidence_bytes: int = 65536

    def __post_init__(self):
        for value, ceiling in ((self.total_seconds, 60), (self.stop_seconds, 20), (self.command_seconds, 15)):
            require(type(value) in (int, float) and math.isfinite(value) and 0 < value <= ceiling,
                    "invalid_input", "Invalid inspection time bound")
        for value, ceiling, minimum in ((self.max_entries, 10000, 1), (self.max_depth, 64, 0),
                                        (self.max_evidence_bytes, 65536, 1)):
            require(type(value) is int and minimum <= value <= ceiling,
                    "invalid_input", "Invalid inspection scan/evidence bound")


@dataclass(frozen=True)
class MountIdentity:
    device: int
    inode: int
    mount_id: int

    def __post_init__(self):
        require(all(type(value) is int and value >= 0 for value in (self.device, self.inode, self.mount_id)),
                "unsafe_storage", "Invalid trusted mount identity")

    @classmethod
    def from_descriptor(cls, descriptor):
        value = os.fstat(descriptor)
        return cls(value.st_dev, value.st_ino, _mount_id(descriptor))


@dataclass(frozen=True)
class InspectionPrerequisites:
    mount_identity: MountIdentity
    privileged_xattrs: bool


@dataclass(frozen=True)
class SourceLease:
    cooperative: bool
    external_admin_excluded: bool


@dataclass(frozen=True)
class StorageObservation:
    descriptor: int
    owner_uid: int
    xattrs: object


@dataclass(frozen=True)
class HandoffReceipt:
    token: str
    source_identity: MountIdentity
    staging_path: str
    staging_verified: bool
    read_only: bool
    nonrecursive: bool
    propagation: str

    def validate(self, source_identity, storage_root):
        hash_value(self.token)
        path = PurePosixPath(self.staging_path) if isinstance(self.staging_path, str) else PurePosixPath(".")
        require(path.is_absolute() and path != PurePosixPath("/") and str(path) == self.staging_path and
                ".." not in path.parts and not path.is_relative_to(PurePosixPath(storage_root)) and
                not path.is_relative_to(PurePosixPath("/proc")) and
                not path.is_relative_to(PurePosixPath("/dev/fd")),
                "unsafe_storage", "Invalid descriptor handoff staging location")
        require(self.source_identity == source_identity and self.staging_verified is True and
                self.read_only is True and self.nonrecursive is True and self.propagation == "rprivate",
                "unsafe_storage", "Descriptor handoff is not pinned and read-only")


@dataclass(frozen=True)
class InspectorSpec:
    image: str
    baseline_commit: str
    run_branch: str
    nonce: str
    source_container_id: str
    source_checkpoint_sha256: str

    def configuration(self):
        # Immutable trusted probe only. No project command, profile mount, OpenCode
        # server, network, socket or credential capability is inherited.
        return {"image": self.image, "uid": 10001, "read_only_root": True, "network_mode": "none",
                "cap_drop": ["ALL"], "no_new_privileges": True, "cpus": "0.25", "memory_mb": 96,
                "memory_swap_mb": 96, "pids_limit": 32, "disk_mb": 64, "tmpfs_mb": 8,
                "log_max_bytes": 1048576, "log_max_files": 1, "log_compress": False,
                "target": "/retained", "read_only_bind": True, "bind_recursive": False,
                "bind_propagation": "rprivate", "probe": "trusted-retained-inspection-v1",
                "baseline_commit": self.baseline_commit, "run_branch": self.run_branch,
                "nonce": self.nonce, "source_container_id": self.source_container_id,
                "source_checkpoint_sha256": self.source_checkpoint_sha256}

    @property
    def configuration_sha256(self):
        return digest(canonical(self.configuration()))


@dataclass(frozen=True)
class InspectorObservation:
    container_id: str
    nonce: str
    configuration_sha256: str
    handoff_token: str


@dataclass(frozen=True)
class CollectedInspection:
    container_id: str
    nonce: str
    exit_code: int
    evidence: bytes


@dataclass(frozen=True)
class InspectorStop:
    container_id: str
    nonce: str
    stopped: bool


@dataclass(frozen=True)
class InspectionResult:
    inspection_id: str
    outcome: str
    diagnostic: object
    inspector_container_id: object
    stop_confirmed: bool
    handoff_release_confirmed: bool
    lease_release_confirmed: bool
    source_unchanged: bool
    evidence_sha256: object
    qualified: bool = False


class DisabledInspectionAdapter:
    def preflight(self, binding, mount_identity, timeout):
        raise RoutineError("storage_inspection_unavailable", "Production retained inspection is not enabled")


class InspectionAuthority(Protocol):
    def source_lease(self, request: InspectionRequest, timeout: float) -> ContextManager[SourceLease]:
        """Acquire the existing cooperative source lock; deny unfinished/held inspections.

        External Docker administrators must additionally be excluded by approved
        maintenance ownership. A flock alone cannot establish that exclusion.
        Context exit must be nonblocking and release only this helper's lease.
        """
        ...

    def read_run(self, request: InspectionRequest, timeout: float) -> dict:
        """Read trusted durable ownership by identifiers, without adopting/editing it."""
        ...


class CheckpointSink(Protocol):
    def __call__(self, record: dict) -> None:
        """Atomically retain a separate inspection record or raise; never edit baseline.

        Reserve the request/nonce on first write, refuse conflicts or existing held
        work, preserve intent on interruption, and bound/nonblock every write.
        """
        ...


class InspectionAdapter(Protocol):
    """Trusted injection seam, NOT qualified privilege or mount transport.

    Every operation (including context entry) must enforce the supplied timeout
    with bounded/reaped descendants. Context exits must be nonblocking. Creation
    requires absence/no-recreate; ambiguous effects are retained, never adopted.
    """
    def preflight(self, binding, mount_identity, timeout) -> InspectionPrerequisites: ...
    def read_source(self, binding, container_id, timeout) -> tuple: ...
    def pin_storage(self, binding, timeout) -> ContextManager[StorageObservation]: ...
    def handoff(self, checkout_fd, checkout_identity, nonce, timeout) -> HandoffReceipt: ...
    def create_inspector(self, spec, handoff, timeout) -> str: ...
    def verify_inspector(self, spec, container_id, handoff, timeout) -> InspectorObservation:
        """Attest nonce, full effective spec and exact pinned staging bind identity."""
        ...
    def start_inspector(self, spec, container_id, timeout) -> None: ...
    def collect(self, spec, container_id, max_bytes, timeout) -> CollectedInspection: ...
    def stop_confirmed(self, spec, container_id, timeout) -> InspectorStop:
        """Verify nonce/immutable ID before stop; positively confirm no live inspector."""
        ...
    def release_handoff(self, receipt, timeout) -> bool:
        """Unmount only the receipt-owned staging mount after confirmed stopping."""
        ...
