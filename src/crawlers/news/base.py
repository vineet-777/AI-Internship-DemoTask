"""Shared RSS news adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.crawlers.base import SourceAdapter
from src.crawlers.feeds import parse_feed
from src.fetch.http_client import AsyncHttpClient, RawResponse
from src.parsing.full_text import extract_full_text


@dataclass(frozen=True, slots=True)
class NewsCandidate:
    original_url: str
    canonical_url: str
    title: str
    body: str
    author: str | None
    published_at: datetime | None
    date_source: str | None
    date_confidence: float
    category: str = "AI"


class RSSNewsAdapter(SourceAdapter[NewsCandidate]):
    def __init__(self, source_id: str, source_name: str, feed_url: str, http_client: AsyncHttpClient) -> None:
        self.source_id = source_id
        self.source_name = source_name
        self._feed_url = feed_url
        self._http_client = http_client

    async def discover(self) -> list[str]:
        return [self._feed_url]

    async def fetch(self, url: str) -> RawResponse:
        return await self._http_client.fetch(url)

    def parse(self, response: RawResponse) -> list[NewsCandidate]:
        return [
            NewsCandidate(item.url, item.canonical_url, item.title, item.description, item.author, item.published_at, item.date_source, item.date_confidence)
            for item in parse_feed(response)
        ]

    async def enrich(self, candidate: NewsCandidate) -> tuple[NewsCandidate, RawResponse | None]:
        """Fetch the original article page and extract full-text content and high-precision date."""
        try:
            response = await self._http_client.fetch(candidate.original_url)

            # Fall back to Playwright when the HTTP response looks like an anti-bot
            # challenge or contains too little useful content to extract from.
            from src.fetch.playwright_client import should_use_browser_fallback, fetch_with_playwright
            if should_use_browser_fallback(response.status_code, response.body):
                try:
                    response = await fetch_with_playwright(candidate.original_url)
                except Exception:
                    pass  # keep the original HTTP response

            extracted = extract_full_text(response.body.decode("utf-8", errors="replace"), fallback_description=candidate.body)
            enriched = NewsCandidate(
                original_url=candidate.original_url,
                canonical_url=candidate.canonical_url,
                title=extracted.title or candidate.title,
                body=extracted.body if len(extracted.body) >= len(candidate.body) else candidate.body,
                author=extracted.author or candidate.author,
                published_at=extracted.published_date or candidate.published_at,
                date_source=extracted.date_source or candidate.date_source,
                date_confidence=max(extracted.date_confidence, candidate.date_confidence),
                category=candidate.category,
            )
            return enriched, response
        except Exception:
            return candidate, None
