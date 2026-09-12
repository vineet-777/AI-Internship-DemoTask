"""Asynchronous per-host token-bucket rate limiting."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketRateLimiter:
    """Limit request starts independently for each hostname.

    Each host starts with ``burst`` tokens. Tokens refill continuously at
    ``rate_per_second`` and one token is consumed per acquired request.
    """

    def __init__(
        self,
        rate_per_second: float,
        burst: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        if burst < 1:
            raise ValueError("burst must be positive")
        self._rate = rate_per_second
        self._burst = float(burst)
        self._clock = clock
        self._sleep = sleep
        self._buckets: dict[str, _Bucket] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def acquire(self, host: str) -> None:
        """Wait until one token is available for ``host`` and consume it."""
        normalized_host = host.strip().casefold()
        if not normalized_host:
            raise ValueError("host must not be empty")
        lock = self._locks.setdefault(normalized_host, asyncio.Lock())
        async with lock:
            bucket = self._buckets.setdefault(
                normalized_host,
                _Bucket(tokens=self._burst, updated_at=self._clock()),
            )
            while True:
                now = self._clock()
                elapsed = max(0.0, now - bucket.updated_at)
                bucket.tokens = min(self._burst, bucket.tokens + elapsed * self._rate)
                bucket.updated_at = now
                if bucket.tokens >= 1.0:
                    bucket.tokens -= 1.0
                    return
                wait_seconds = (1.0 - bucket.tokens) / self._rate
                await self._sleep(wait_seconds)
