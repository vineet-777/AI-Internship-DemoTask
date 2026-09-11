"""Bounded retry behaviour for explicitly transient failures."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float
    jitter_seconds: float

    def delay_for(self, failed_attempt: int, retry_after: str | None = None) -> float:
        """Calculate a bounded delay, honoring a valid server Retry-After value."""
        retry_after_seconds = _parse_retry_after(retry_after)
        exponential_delay = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2 ** (failed_attempt - 1)),
        )
        baseline = max(exponential_delay, retry_after_seconds or 0.0)
        return baseline + random.uniform(0.0, self.jitter_seconds)


class RetryableFailure(Exception):
    """A failure whose request may safely be retried under the configured budget."""

    def __init__(self, message: str, *, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


async def retry_async(
    operation: Callable[[int], Awaitable[T]],
    *,
    policy: RetryPolicy,
    should_retry: Callable[[Exception], bool],
    on_retry: Callable[[Exception, int, float], Awaitable[None] | None] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Run an async operation with bounded retries for a caller-defined failure set."""
    if policy.max_attempts < 1:
        raise ValueError("max_attempts must be at least one")

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await operation(attempt)
        except Exception as exc:
            if attempt >= policy.max_attempts or not should_retry(exc):
                raise
            retry_after = exc.retry_after if isinstance(exc, RetryableFailure) else None
            delay = policy.delay_for(attempt, retry_after)
            if on_retry:
                callback_result = on_retry(exc, attempt, delay)
                if callback_result is not None:
                    await callback_result
            await sleep(delay)

    raise RuntimeError("Retry loop exited unexpectedly")


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, (retry_at - retry_at.now(retry_at.tzinfo)).total_seconds())
