"""Bounded injectable Docker API/admin transports. No executable default backend."""
from copy import deepcopy
import math
import time

from .contracts import RoutineError, canonical, digest, require


class Budget:
    def __init__(self, timeout, clock=time.monotonic):
        require(type(timeout) in (int, float) and math.isfinite(timeout) and timeout > 0,
                "command_timeout", "A finite positive transport deadline is required")
        self.clock, self.deadline = clock, clock() + timeout

    def remaining(self):
        value = self.deadline - self.clock()
        require(value > 0, "command_timeout", "Network operation deadline exhausted")
        return value

    def call(self, operation, *args):
        result = operation(*args, self.remaining())
        self.remaining()  # Late success is failure, including a late readback.
        return result


class DockerNetworkTransport:
    """request(method, path, body, timeout) returns decoded Docker API JSON.

    The injected caller owns a pinned local daemon/socket, bounded response bytes,
    status validation and cancellation. Never inherits Docker contexts or secrets.
    """
    def __init__(self, request=None):
        self.request = request

    def call(self, method, path, body, timeout):
        require(self.request is not None, "policy_unavailable", "Docker networking transport is not configured")
        try:
            result = self.request(method, path, deepcopy(body), timeout)
            require(len(canonical(result)) <= 1048576, "adapter_failed", "Docker response exceeds its bound")
            return result
        except (OSError, ValueError, TypeError) as exc:
            raise RoutineError("adapter_failed", "Docker networking transport failed") from exc


class NetworkAdminTransport:
    """exchange(operation, payload, timeout) is a trusted, separately approved helper.

    apply/read operations are distinct. A returned hash/boolean alone is never an
    effective-rules readback. This class installs nothing and invokes no programs.
    """
    def __init__(self, exchange=None):
        self.exchange = exchange

    def call(self, operation, payload, timeout):
        require(self.exchange is not None, "policy_unavailable", "Trusted network/bootstrap transport is not configured")
        try:
            result = self.exchange(operation, deepcopy(payload), timeout)
            require(len(canonical(result)) <= 1048576, "adapter_failed", "Administration response exceeds its bound")
            return result
        except (OSError, ValueError, TypeError) as exc:
            raise RoutineError("adapter_failed", "Network administration transport failed") from exc


def fingerprint(value):
    return digest(canonical(value))
