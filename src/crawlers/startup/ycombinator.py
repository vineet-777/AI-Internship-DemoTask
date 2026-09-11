"""YC directory adapter using its server-rendered JSON-LD organization data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from html.parser import HTMLParser
from math import ceil
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.config.settings import _load_yaml
from src.crawlers.startup.base import StartupCandidate, StartupSourceAdapter
from src.fetch.http_client import AsyncHttpClient, RawResponse
from src.parsing.identity import canonicalize_url


class StartupParseError(ValueError):
    """The source response does not contain safe startup records."""


@dataclass(frozen=True, slots=True)
class YCombinatorSourceSettings:
    id: str
    name: str
    listing_url: str
    page_size: int
    max_records: int
    enabled: bool


class YCombinatorAdapter(StartupSourceAdapter):
    """Discover up to the configured target through deterministic page URLs."""

    def __init__(self, settings: YCombinatorSourceSettings, http_client: AsyncHttpClient) -> None:
        if settings.page_size < 1 or settings.max_records < 1:
            raise ValueError("YC page_size and max_records must be positive")
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

    def parse(self, response: RawResponse) -> list[StartupCandidate]:
        parser = _JsonLdParser()
        parser.feed(response.body.decode("utf-8"))
        candidates: list[StartupCandidate] = []
        seen_urls: set[str] = set()
        for item in parser.items:
            candidate = _candidate_from_json_ld(item)
            if candidate is None or candidate.canonical_url in seen_urls:
                continue
            seen_urls.add(candidate.canonical_url)
            candidates.append(candidate)
        return candidates


def load_ycombinator_source(path: str | Path = "configs/sources.yaml") -> YCombinatorSourceSettings:
    for source in _load_yaml(Path(path)).get("sources", []):
        if source.get("id") == "ycombinator":
            return YCombinatorSourceSettings(
                id=str(source["id"]),
                name=str(source["name"]),
                listing_url=str(source["listing_url"]),
                page_size=int(source["page_size"]),
                max_records=int(source["max_records"]),
                enabled=bool(source["enabled"]),
            )
    raise ValueError("configs/sources.yaml does not define a ycombinator source")


def _with_page(url: str, page: int) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _candidate_from_json_ld(item: dict[str, Any]) -> StartupCandidate | None:
    if item.get("@type") not in {"Organization", "Corporation", "LocalBusiness"}:
        return None
    name = item.get("name")
    url = item.get("url")
    if not isinstance(name, str) or not name.strip() or not isinstance(url, str):
        return None
    try:
        canonical = canonicalize_url(url)
    except ValueError:
        return None
    address = item.get("address")
    headquarters = _address_text(address)
    data: dict[str, Any] = {
        "description": _string(item.get("description")),
        "headquarters": headquarters,
        "website": _string(item.get("sameAs")) if isinstance(item.get("sameAs"), str) else None,
        "foundedYear": _year(item.get("foundingDate")),
        "employeeCount": _employee_count(item.get("numberOfEmployees")),
        "rawEntityName": name.strip(),
    }
    return StartupCandidate(
        original_url=url,
        canonical_url=canonical,
        entity_name=name.strip(),
        data={key: value for key, value in data.items() if value is not None},
    )


def _address_text(value: object) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if not isinstance(value, dict):
        return None
    parts = [value.get(key) for key in ("streetAddress", "addressLocality", "addressRegion", "addressCountry")]
    text = ", ".join(part.strip() for part in parts if isinstance(part, str) and part.strip())
    return text or None


def _employee_count(value: object) -> int | None:
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, dict):
        for key in ("value", "minValue"):
            count = value.get(key)
            if isinstance(count, int) and count >= 0:
                return count
    return None


def _year(value: object) -> int | None:
    if isinstance(value, int) and 1800 <= value <= 2100:
        return value
    if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
        year = int(value[:4])
        return year if 1800 <= year <= 2100 else None
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
        if isinstance(values, dict):
            values = [values]
        self.items.extend(value for value in values if isinstance(value, dict))
