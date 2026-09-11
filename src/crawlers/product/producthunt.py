"""Product Hunt adapter using server-rendered JSON-LD product metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from html.parser import HTMLParser
from math import ceil
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.config.settings import _load_yaml
from src.crawlers.product.base import ProductCandidate, ProductSourceAdapter
from src.fetch.http_client import AsyncHttpClient, RawResponse
from src.parsing.identity import canonicalize_url
from src.schemas.product import PricingModel


class ProductParseError(ValueError):
    """The source response does not contain safe product records."""


@dataclass(frozen=True, slots=True)
class ProductHuntSourceSettings:
    id: str
    name: str
    listing_url: str
    page_size: int
    max_records: int
    enabled: bool


class ProductHuntAdapter(ProductSourceAdapter):
    """Discover up to the configured target through deterministic page URLs."""

    def __init__(self, settings: ProductHuntSourceSettings, http_client: AsyncHttpClient) -> None:
        if settings.page_size < 1 or settings.max_records < 1:
            raise ValueError("Product Hunt page_size and max_records must be positive")
        self.source_id = settings.id
        self.source_name = settings.name
        self._listing_url = settings.listing_url
        self._page_size = settings.page_size
        self._max_records = settings.max_records
        self._http_client = http_client

    async def discover(self) -> list[str]:
        return [
            _with_page(self._listing_url, page)
            for page in range(1, ceil(self._max_records / self._page_size) + 1)
        ]

    async def fetch(self, url: str) -> RawResponse:
        return await self._http_client.fetch(url)

    def parse(self, response: RawResponse) -> list[ProductCandidate]:
        parser = _JsonLdParser()
        parser.feed(response.body.decode("utf-8"))
        candidates: list[ProductCandidate] = []
        seen_urls: set[str] = set()
        for item in parser.items:
            candidate = _candidate_from_json_ld(item)
            if candidate is None or candidate.canonical_url in seen_urls:
                continue
            seen_urls.add(candidate.canonical_url)
            candidates.append(candidate)
        return candidates


def load_product_hunt_source(path: str | Path = "configs/sources.yaml") -> ProductHuntSourceSettings:
    for source in _load_yaml(Path(path)).get("sources", []):
        if source.get("id") == "product_hunt":
            return ProductHuntSourceSettings(
                id=str(source["id"]),
                name=str(source["name"]),
                listing_url=str(source["listing_url"]),
                page_size=int(source["page_size"]),
                max_records=int(source["max_records"]),
                enabled=bool(source["enabled"]),
            )
    raise ValueError("configs/sources.yaml does not define a product_hunt source")


def _with_page(url: str, page: int) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _candidate_from_json_ld(item: dict[str, Any]) -> ProductCandidate | None:
    item_type = item.get("@type")
    types = set(item_type) if isinstance(item_type, list) else {item_type}
    if not types.intersection({"Product", "SoftwareApplication", "WebApplication"}):
        return None
    product_name = _string(item.get("name"))
    product_url = _string(item.get("url"))
    startup_name = _organization_name(item.get("brand"), item.get("manufacturer"), item.get("author"), item.get("provider"))
    if not product_name or not product_url or not startup_name:
        return None
    try:
        canonical = canonicalize_url(product_url)
    except ValueError:
        return None
    pricing_model = _pricing_model(item)
    if pricing_model is None:
        return None
    data: dict[str, Any] = {
        "description": _string(item.get("description")),
        "website": product_url,
        "rawStartupName": startup_name,
    }
    return ProductCandidate(
        original_url=product_url,
        canonical_url=canonical,
        product_name=product_name,
        startup_name=startup_name,
        pricing_model=pricing_model,
        data={key: value for key, value in data.items() if value is not None},
    )


def _organization_name(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            name = value.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def _pricing_model(item: dict[str, Any]) -> PricingModel | None:
    explicit = _string(item.get("pricingModel"))
    if explicit:
        normalized = explicit.upper().replace("-", "_")
        if normalized in {"FREE", "FREEMIUM", "PAID", "ENTERPRISE"}:
            return normalized  # type: ignore[return-value]
    if item.get("isAccessibleForFree") is True:
        return "FREE"
    offers = item.get("offers")
    offer_values = offers if isinstance(offers, list) else [offers]
    for offer in offer_values:
        if not isinstance(offer, dict):
            continue
        description = (_string(offer.get("description")) or "").upper()
        if "ENTERPRISE" in description:
            return "ENTERPRISE"
        if "FREEMIUM" in description:
            return "FREEMIUM"
        price = offer.get("price")
        if isinstance(price, (int, float)):
            return "FREE" if price == 0 else "PAID"
        if isinstance(price, str) and price.strip() in {"0", "0.0", "0.00"}:
            return "FREE"
    return None


def _string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


class _JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.items: list[dict[str, Any]] = []
        self._in_json_ld = False
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and dict(attrs).get("type") == "application/ld+json":
            self._in_json_ld = True
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "script" or not self._in_json_ld:
            return
        self._in_json_ld = False
        try:
            payload = json.loads("".join(self._buffer))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if isinstance(payload, list):
            values = payload
        elif isinstance(payload, dict):
            graph = payload.get("@graph")
            values = graph if isinstance(graph, list) else [payload]
        else:
            values = []
        self.items.extend(value for value in values if isinstance(value, dict))
