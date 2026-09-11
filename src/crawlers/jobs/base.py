"""Shared RSS job adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.crawlers.base import SourceAdapter
from src.crawlers.feeds import parse_feed
from src.fetch.http_client import AsyncHttpClient, RawResponse


@dataclass(frozen=True, slots=True)
class JobCandidate:
    original_url: str
    canonical_url: str
    company: str
    title: str
    description: str
    published_at: datetime | None
    date_source: str | None
    date_confidence: float
    is_remote: bool
    role_family: str | None


class RSSJobAdapter(SourceAdapter[JobCandidate]):
    def __init__(self, source_id: str, source_name: str, feed_url: str, http_client: AsyncHttpClient) -> None:
        self.source_id = source_id
        self.source_name = source_name
        self._feed_url = feed_url
        self._http_client = http_client

    async def discover(self) -> list[str]:
        return [self._feed_url]

    async def fetch(self, url: str) -> RawResponse:
        return await self._http_client.fetch(url)

    def parse(self, response: RawResponse) -> list[JobCandidate]:
        candidates: list[JobCandidate] = []
        for item in parse_feed(response):
            text = f"{item.title} {item.description}".casefold()
            candidates.append(
                JobCandidate(
                    original_url=item.url,
                    canonical_url=item.canonical_url,
                    company=item.author or "Unknown company",
                    title=item.title,
                    description=item.description,
                    published_at=item.published_at,
                    date_source=item.date_source,
                    date_confidence=item.date_confidence,
                    is_remote="remote" in text,
                    role_family=_role_family(text),
                )
            )
        return candidates


def _role_family(text: str) -> str | None:
    for keyword, family in (("engineer", "Engineering"), ("research", "Research"), ("design", "Design"), ("sales", "Sales"), ("marketing", "Marketing"), ("product", "Product")):
        if keyword in text:
            return family
    return None
