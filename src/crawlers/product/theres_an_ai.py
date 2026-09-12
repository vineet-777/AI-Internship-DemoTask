"""Directory adapter for There's An AI For That product directory."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from math import ceil
from typing import Any

from src.crawlers.product.base import ProductCandidate, ProductSourceAdapter
from src.fetch.http_client import AsyncHttpClient, RawResponse
from src.parsing.identity import canonicalize_url
from src.schemas.product import PricingModel


@dataclass(frozen=True, slots=True)
class TheresAnAiSettings:
    id: str
    name: str
    listing_url: str
    page_size: int
    max_records: int
    enabled: bool


class TheresAnAiAdapter(ProductSourceAdapter):
    """Acquire AI product records from There's An AI For That."""

    def __init__(self, settings: TheresAnAiSettings, http_client: AsyncHttpClient) -> None:
        self.source_id = settings.id
        self.source_name = settings.name
        self._listing_url = settings.listing_url.rstrip("/")
        self._page_size = settings.page_size
        self._max_records = settings.max_records
        self._http_client = http_client

    async def discover(self) -> list[str]:
        pages = ceil(self._max_records / self._page_size)
        return [f"{self._listing_url}/page/{p}/" if p > 1 else self._listing_url for p in range(1, pages + 1)]

    async def fetch(self, url: str) -> RawResponse:
        return await self._http_client.fetch(url)

    def parse(self, response: RawResponse) -> list[ProductCandidate]:
        candidates: list[ProductCandidate] = []
        html = response.body.decode("utf-8", errors="replace")

        # Extract product cards using regex/html patterns
        # Standard card pattern: <a ... class="...ai_link..." href="..."> name </a>
        card_pattern = re.compile(
            r'<li[^>]*class="[^"]*ai_item[^"]*"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>.*?<h2[^>]*>([^<]+)</h2>(.*?)</li>',
            re.DOTALL | re.IGNORECASE,
        )

        for match in card_pattern.finditer(html):
            rel_url = match.group(1).strip()
            name = match.group(2).strip()
            snippet = match.group(3)

            if not rel_url.startswith("http"):
                product_url = f"https://theresanaiforthat.com{rel_url}"
            else:
                product_url = rel_url

            try:
                canonical = canonicalize_url(product_url)
            except Exception:
                continue

            # Pricing detection
            pricing: PricingModel = "FREEMIUM"
            lowered = snippet.casefold()
            if "free" in lowered and "trial" not in lowered:
                pricing = "FREE"
            elif "paid" in lowered or "pricing" in lowered:
                pricing = "PAID"
            elif "enterprise" in lowered or "contact" in lowered:
                pricing = "ENTERPRISE"

            desc_match = re.search(r'<p[^>]*class="[^"]*desc[^"]*"[^>]*>([^<]+)</p>', snippet, re.IGNORECASE)
            desc = desc_match.group(1).strip() if desc_match else f"{name} AI tool"

            candidates.append(
                ProductCandidate(
                    original_url=product_url,
                    canonical_url=canonical,
                    product_name=name,
                    startup_name=name,  # Product name used as canonical venture creator
                    pricing_model=pricing,
                    data={
                        "productName": name,
                        "startupName": name,
                        "pricingModel": pricing,
                        "description": desc,
                        "website": product_url,
                    },
                )
            )

        return candidates
