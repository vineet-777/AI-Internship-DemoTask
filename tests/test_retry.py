from __future__ import annotations

import httpx

from src.fetch.http_client import AsyncHttpClient
from src.fetch.rate_limiter import TokenBucketRateLimiter
from src.fetch.retry import RetryPolicy


async def test_timeout_is_retried_then_fetch_succeeds() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, content=b"ok", headers={"content-type": "application/xml"})

    async with AsyncHttpClient(
        timeout_seconds=1,
        connect_timeout_seconds=1,
        max_concurrency=1,
        retry_policy=RetryPolicy(2, 0, 0, 0),
        user_agent="test-agent",
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await client.fetch("https://example.test/source")

    assert calls == 2
    assert response.body == b"ok"
    assert response.attempts == 2


async def test_http_client_applies_rate_limit_to_each_retry_attempt() -> None:
    calls = 0
    acquired_hosts: list[str] = []

    class RecordingLimiter(TokenBucketRateLimiter):
        async def acquire(self, host: str) -> None:
            acquired_hosts.append(host)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, content=b"ok", request=request)

    async with AsyncHttpClient(
        timeout_seconds=1,
        connect_timeout_seconds=1,
        max_concurrency=1,
        retry_policy=RetryPolicy(2, 0, 0, 0),
        user_agent="test-agent",
        transport=httpx.MockTransport(handler),
        rate_limiter=RecordingLimiter(1, 1),
    ) as client:
        await client.fetch("https://example.test:8443/source")

    assert acquired_hosts == ["example.test:8443", "example.test:8443"]
