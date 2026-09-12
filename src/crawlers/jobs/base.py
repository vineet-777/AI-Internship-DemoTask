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

    async def enrich(self, candidate: JobCandidate) -> tuple[JobCandidate, RawResponse | None]:
        """Fetch the original job posting page and extract full-text content and high-precision date."""
        from src.parsing.full_text import extract_full_text

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

            extracted = extract_full_text(response.body.decode("utf-8", errors="replace"), fallback_description=candidate.description)
            text = f"{candidate.title} {extracted.body}".casefold()
            enriched = JobCandidate(
                original_url=candidate.original_url,
                canonical_url=candidate.canonical_url,
                company=candidate.company,
                title=extracted.title or candidate.title,
                description=extracted.body if len(extracted.body) >= len(candidate.description) else candidate.description,
                published_at=extracted.published_date or candidate.published_at,
                date_source=extracted.date_source or candidate.date_source,
                date_confidence=max(extracted.date_confidence, candidate.date_confidence),
                is_remote=candidate.is_remote or ("remote" in text),
                role_family=candidate.role_family or _role_family(text),
            )
            return enriched, response
        except Exception:
            return candidate, None


def _role_family(text: str) -> str | None:
    for keyword, family in (("engineer", "Engineering"), ("research", "Research"), ("design", "Design"), ("sales", "Sales"), ("marketing", "Marketing"), ("product", "Product")):
        if keyword in text:
            return family
    return None
