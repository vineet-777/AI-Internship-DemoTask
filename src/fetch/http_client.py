"""Shared, concurrency-bounded asynchronous HTTP client."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from src.fetch.retry import RetryPolicy, RetryableFailure, retry_async
from src.fetch.rate_limiter import TokenBucketRateLimiter
from src.observability.logging import log_event


class InvalidUrlError(ValueError):
    """The URL is malformed and must not be retried."""


class HttpStatusError(RetryableFailure):
    """An HTTP failure with the status and request context preserved."""

    def __init__(self, response: httpx.Response) -> None:
        super().__init__(
            f"HTTP {response.status_code} for {response.request.url}",
            retry_after=response.headers.get("Retry-After"),
        )
        self.status_code = response.status_code
        self.url = str(response.request.url)

    @property
    def is_transient(self) -> bool:
        return self.status_code == 429 or 500 <= self.status_code <= 599


@dataclass(frozen=True, slots=True)
class RawResponse:
    request_url: str
    response_url: str
    status_code: int
    headers: dict[str, str]
    body: bytes
    retrieved_at: datetime
    attempts: int


class AsyncHttpClient:
    """One pooled httpx client reused for all requests in an ingestion run."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        connect_timeout_seconds: float,
        max_concurrency: int,
        retry_policy: RetryPolicy,
        user_agent: str,
        transport: httpx.AsyncBaseTransport | None = None,
        rate_limiter: TokenBucketRateLimiter | None = None,
    ) -> None:
        self._retry_policy = retry_policy
        self._rate_limiter = rate_limiter
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            headers={"User-Agent": user_agent, "Accept": "application/atom+xml, application/xml;q=0.9, */*;q=0.1"},
            timeout=httpx.Timeout(timeout_seconds, connect=connect_timeout_seconds),
            limits=httpx.Limits(max_connections=max_concurrency, max_keepalive_connections=max_concurrency),
            transport=transport,
        )

    async def __aenter__(self) -> "AsyncHttpClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(self, url: str, *, headers: dict[str, str] | None = None) -> RawResponse:
        _validate_http_url(url)
        async with self._semaphore:
            return await retry_async(
                lambda attempt: self._fetch_once(url, attempt, headers),
                policy=self._retry_policy,
                should_retry=_is_retryable,
                on_retry=lambda error, attempt, delay: _log_retry(url, error, attempt, delay),
            )

    async def _fetch_once(
        self,
        url: str,
        attempt: int,
        headers: dict[str, str] | None,
    ) -> RawResponse:
        if self._rate_limiter is not None:
            parsed_url = urlsplit(url)
            if not parsed_url.netloc:  # validated by fetch(); retained defensively for direct calls
                raise InvalidUrlError(f"Expected an absolute HTTP(S) URL, got {url!r}")
            await self._rate_limiter.acquire(parsed_url.netloc)
        try:
            response = await self._client.get(url, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise RetryableFailure(f"network failure for {url}: {exc}") from exc

        if response.status_code >= 400:
            error = HttpStatusError(response)
            if error.is_transient:
                raise error
            raise RuntimeError(str(error)) from error

        raw_response = RawResponse(
            request_url=url,
            response_url=str(response.url),
            status_code=response.status_code,
            headers=dict(response.headers),
            body=response.content,
            retrieved_at=datetime.now(UTC),
            attempts=attempt,
        )
        log_event(
            "http_fetch_succeeded",
            url=url,
            response_url=raw_response.response_url,
            status=raw_response.status_code,
            attempt=attempt,
            bytes=len(raw_response.body),
        )
        return raw_response


def _validate_http_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise InvalidUrlError(f"Expected an absolute HTTP(S) URL, got {url!r}")


def _is_retryable(error: Exception) -> bool:
    return isinstance(error, RetryableFailure)


async def _log_retry(url: str, error: Exception, attempt: int, delay: float) -> None:
    log_event(
        "http_fetch_retry",
        url=url,
        attempt=attempt,
        delay_seconds=round(delay, 3),
        error_type=type(error).__name__,
        status=getattr(error, "status_code", None),
    )
