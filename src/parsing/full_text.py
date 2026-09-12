"""Full-text and publication date extraction for news articles and job postings."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Any

DATE_META_KEYS = (
    "article:published_time",
    "og:published_time",
    "pubdate",
    "publishdate",
    "date",
    "dc.date",
    "dc.date.issued",
    "parsely-pub-date",
    "sailthru.date",
)

BOILERPLATE_TAGS = {
    "script",
    "style",
    "nav",
    "header",
    "footer",
    "aside",
    "noscript",
    "svg",
    "form",
    "button",
}


@dataclass(frozen=True, slots=True)
class ExtractedContent:
    title: str | None
    body: str
    published_date: datetime | None
    date_source: str | None
    date_confidence: float
    author: str | None = None


class _HTMLContentExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.author: str | None = None
        self.meta_dates: list[tuple[str, str]] = []
        self.json_ld_dates: list[str] = []
        self.json_ld_authors: list[str] = []
        self.time_tag_dates: list[str] = []

        self._tag_stack: list[str] = []
        self._current_tag: str | None = None
        self._in_title = False
        self._in_json_ld = False
        self._json_ld_buffer: list[str] = []

        self._article_buffer: list[str] = []
        self._paragraph_buffer: list[str] = []
        self._all_text_buffer: list[str] = []
        self._in_article = False
        self._in_p = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k.casefold(): (v or "") for k, v in attrs}
        self._tag_stack.append(tag)
        self._current_tag = tag

        if tag in BOILERPLATE_TAGS:
            if tag == "script" and attr_dict.get("type") == "application/ld+json":
                self._in_json_ld = True
                self._json_ld_buffer = []
            return

        if tag == "title" and not self.title:
            self._in_title = True

        if tag == "meta":
            prop = attr_dict.get("property") or attr_dict.get("name") or ""
            content = attr_dict.get("content") or ""
            if prop.casefold() in DATE_META_KEYS and content:
                self.meta_dates.append((prop.casefold(), content.strip()))
            if prop.casefold() in ("author", "article:author") and content and not self.author:
                self.author = content.strip()

        if tag == "time":
            dt = attr_dict.get("datetime") or attr_dict.get("data-time") or ""
            if dt:
                self.time_tag_dates.append(dt.strip())

        if tag in ("article", "main") or "article" in attr_dict.get("class", "").casefold():
            self._in_article = True

        if tag == "p":
            self._in_p = True

    def handle_endtag(self, tag: str) -> None:
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()
        self._current_tag = self._tag_stack[-1] if self._tag_stack else None

        if tag == "title":
            self._in_title = False
        elif tag == "p":
            self._in_p = False
            self._paragraph_buffer.append("\n")
        elif tag in ("article", "main"):
            self._in_article = False
        elif tag == "script" and self._in_json_ld:
            self._in_json_ld = False
            self._parse_json_ld("".join(self._json_ld_buffer))

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return

        if self._in_json_ld:
            self._json_ld_buffer.append(data)
            return

        if any(t in BOILERPLATE_TAGS for t in self._tag_stack):
            return

        if self._in_title and not self.title:
            self.title = " ".join(data.split())
            return

        if self._in_article:
            self._article_buffer.append(data)
        if self._in_p:
            self._paragraph_buffer.append(data)
        self._all_text_buffer.append(data)

    def _parse_json_ld(self, raw_json: str) -> None:
        try:
            payload = json.loads(raw_json)
        except Exception:
            return
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if isinstance(item, dict):
                graph = item.get("@graph")
                nodes = graph if isinstance(graph, list) else [item]
                for node in nodes:
                    if isinstance(node, dict):
                        for key in ("datePublished", "dateCreated", "dateModified"):
                            val = node.get(key)
                            if isinstance(val, str) and val.strip():
                                self.json_ld_dates.append(val.strip())
                        author = node.get("author")
                        if isinstance(author, dict) and "name" in author:
                            self.json_ld_authors.append(str(author["name"]))
                        elif isinstance(author, str):
                            self.json_ld_authors.append(author)

    def get_body_text(self) -> str:
        article_text = " ".join("".join(self._article_buffer).split())
        if len(article_text) >= 150:
            return article_text
        paragraph_text = " ".join("".join(self._paragraph_buffer).split())
        if len(paragraph_text) >= 150:
            return paragraph_text
        return " ".join("".join(self._all_text_buffer).split())


def _parse_iso_date(raw: str) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except (ValueError, TypeError):
        pass

    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%a, %d %b %Y %H:%M:%S %z",
        "%d %b %Y",
        "%B %d, %Y",
    ):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except (ValueError, TypeError):
            continue
    return None


def _parse_relative_date(text: str, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now(UTC)
    match = re.search(r"(\d+)\s+(minute|hour|day)s?\s+ago", text, re.IGNORECASE)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "minute":
        return now - timedelta(minutes=amount)
    if unit == "hour":
        return now - timedelta(hours=amount)
    if unit == "day":
        return now - timedelta(days=amount)
    return None


def extract_full_text(html: str, fallback_description: str = "") -> ExtractedContent:
    """Extract readable body text and publication date from an HTML document."""
    parser = _HTMLContentExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass

    body = parser.get_body_text()
    if len(body) < 50 and fallback_description:
        body = fallback_description

    published_date: datetime | None = None
    date_source: str | None = None
    confidence: float = 0.0

    for raw in parser.json_ld_dates:
        parsed = _parse_iso_date(raw)
        if parsed:
            published_date = parsed
            date_source = "json_ld"
            confidence = 0.95
            break

    if not published_date:
        for source, raw in parser.meta_dates:
            parsed = _parse_iso_date(raw)
            if parsed:
                published_date = parsed
                date_source = "meta"
                confidence = 0.90
                break

    if not published_date:
        for raw in parser.time_tag_dates:
            parsed = _parse_iso_date(raw)
            if parsed:
                published_date = parsed
                date_source = "time"
                confidence = 0.85
                break

    if not published_date:
        rel = _parse_relative_date(body[:1000])
        if rel:
            published_date = rel
            date_source = "relative"
            confidence = 0.75

    author = parser.author or (parser.json_ld_authors[0] if parser.json_ld_authors else None)

    return ExtractedContent(
        title=parser.title,
        body=body,
        published_date=published_date,
        date_source=date_source,
        date_confidence=confidence,
        author=author,
    )
