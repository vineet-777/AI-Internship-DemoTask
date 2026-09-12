"""Provider circuit breaker used by the LLM orchestrator."""

from __future__ import annotations

import time
from collections.abc import Callable


class CircuitBreaker:
    CLOSED, OPEN, HALF_OPEN = range(3)

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        if recovery_timeout < 0:
            raise ValueError("recovery_timeout must not be negative")
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._clock = clock
        self.state = self.CLOSED
        self.failures = 0
        self.last_failure = 0.0
        self._half_open_probe = False

    @property
    def failure_count(self) -> int:
        return self.failures

    def record_success(self) -> None:
        self.state = self.CLOSED
        self.failures = 0
        self.last_failure = 0.0
        self._half_open_probe = False

    def record_failure(self) -> None:
        if self.state == self.HALF_OPEN:
            self._open()
            return
        self.failures += 1
        self.last_failure = self._clock()
        if self.failures >= self.failure_threshold:
            self._open()

    def can_execute(self) -> bool:
        if self.state == self.CLOSED:
            return True
        if self.state == self.OPEN:
            if self._clock() - self.last_failure < self.recovery_timeout:
                return False
            self.state = self.HALF_OPEN
            self._half_open_probe = False
        if self.state == self.HALF_OPEN:
            if self._half_open_probe:
                return False
            self._half_open_probe = True
            return True
        return False

    def _open(self) -> None:
        self.state = self.OPEN
        self.last_failure = self._clock()
        self._half_open_probe = False
