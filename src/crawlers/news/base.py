"""Shared RSS news adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.crawlers.base import SourceAdapter
from src.crawlers.feeds import parse_feed
from src.fetch.http_client import AsyncHttpClient, RawResponse


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
