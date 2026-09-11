"""Small RSS/Atom parser shared by news and job adapters."""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree

from src.fetch.http_client import RawResponse
from src.freshness.policies import select_date
from src.parsing.identity import canonicalize_url


@dataclass(frozen=True, slots=True)
class FeedItem:
    url: str
    canonical_url: str
    title: str
    description: str
    author: str | None
    published_at: object
    date_source: str | None
    date_confidence: float


def parse_feed(response: RawResponse) -> list[FeedItem]:
    try:
        root = ElementTree.fromstring(response.body)
    except ElementTree.ParseError as exc:
        raise ValueError("Feed response is not valid XML") from exc
    items = root.findall(".//item") or root.findall(".//{*}entry")
    results: list[FeedItem] = []
    for item in items:
        url = _text(item, "link")
        if not url:
            links = item.findall("{*}link")
            url = next((link.attrib.get("href") for link in links if link.attrib.get("href")), None)
        title = _text(item, "title")
        description = _text(item, "description") or _text(item, "{*}encoded") or _text(item, "{*}content")
        rss_date = _text(item, "pubDate") or _text(item, "published") or _text(item, "{*}date") or _text(item, "updated")
        author = _text(item, "author") or _text(item, "{*}creator")
        if not url or not title or not description:
            continue
        try:
            canonical = canonicalize_url(url)
        except ValueError:
            continue
        evidence = select_date(rss_date=rss_date)
        results.append(FeedItem(url, canonical, title, description, author, evidence.published_at, evidence.source, evidence.confidence))
    return results


def _text(element: ElementTree.Element, path: str) -> str | None:
    child = element.find(path)
    if child is None or child.text is None:
        return None
    value = " ".join(child.text.split())
    return value or None
