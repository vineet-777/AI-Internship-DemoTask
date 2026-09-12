from __future__ import annotations

import asyncio

import pytest

from src.fetch.rate_limiter import TokenBucketRateLimiter


async def test_token_bucket_allows_burst_then_waits_for_refill() -> None:
    limiter = TokenBucketRateLimiter(rate_per_second=100, burst=2)
    await limiter.acquire("Example.TEST")
    await limiter.acquire("example.test")

    started = asyncio.get_running_loop().time()
    await limiter.acquire("example.test")
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed >= 0.005


async def test_token_bucket_isolates_hosts() -> None:
    limiter = TokenBucketRateLimiter(rate_per_second=1, burst=1)
    await limiter.acquire("one.example")
    await limiter.acquire("two.example")


@pytest.mark.parametrize("rate, burst", [(0, 1), (-1, 1), (1, 0), (1, -1)])
def test_token_bucket_rejects_invalid_configuration(rate: float, burst: int) -> None:
    with pytest.raises(ValueError):
        TokenBucketRateLimiter(rate, burst)
