"""Date-source priority and hard 24-hour freshness policy."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

DATE_CONFIDENCE = {
    "json_ld": 0.99,
    "meta": 0.95,
    "time": 0.90,
    "source_specific": 0.88,
    "rss": 0.85,
    "visible": 0.70,
    "relative": 0.60,
}


@dataclass(frozen=True, slots=True)
class DateEvidence:
    published_at: datetime | None
    source: str | None
    confidence: float


@dataclass(frozen=True, slots=True)
class FreshnessDecision:
    status: str
    published_at: datetime | None
    source: str | None
    confidence: float
    age_hours: float | None
    reason: str


def select_date(
    *,
    html: str | None = None,
    rss_date: str | datetime | None = None,
    now: datetime | None = None,
) -> DateEvidence:
    reference = _utc(now or datetime.now(UTC))
    parser = _DateMarkupParser()
    if html:
        parser.feed(html)
    candidates = [
        ("json_ld", parser.json_ld),
        ("meta", parser.meta),
        ("time", parser.time),
        ("source_specific", parser.source_specific),
        ("rss", rss_date),
        ("visible", parser.visible),
        ("relative", parser.relative),
    ]
    for source, value in candidates:
        parsed = _parse_date(value, reference)
        if parsed is not None:
            return DateEvidence(parsed, source, DATE_CONFIDENCE[source])
    return DateEvidence(None, None, 0.0)


def evaluate_freshness(
    evidence: DateEvidence,
    *,
    now: datetime | None = None,
    max_age_hours: float = 24.0,
    minimum_confidence: float = 0.75,
) -> FreshnessDecision:
    if evidence.published_at is None:
        return FreshnessDecision("QUARANTINE", None, None, 0.0, None, "date_unresolved")
    published_at = _utc(evidence.published_at)
    age_hours = (_utc(now or datetime.now(UTC)) - published_at).total_seconds() / 3600
    if evidence.confidence < minimum_confidence:
        return FreshnessDecision("QUARANTINE", published_at, evidence.source, evidence.confidence, age_hours, "low_confidence_date")
    if age_hours < 0:
        return FreshnessDecision("REJECT", published_at, evidence.source, evidence.confidence, age_hours, "future_date")
    if age_hours > max_age_hours:
        return FreshnessDecision("REJECT", published_at, evidence.source, evidence.confidence, age_hours, "stale_date")
    return FreshnessDecision("ACCEPT", published_at, evidence.source, evidence.confidence, age_hours, "fresh")


def _parse_date(value: object, reference: datetime) -> datetime | None:
    if isinstance(value, datetime):
        return _utc(value)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return _utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        pass
    try:
        return _utc(parsedate_to_datetime(text))
    except (TypeError, ValueError, OverflowError):
        pass
    relative = re.fullmatch(r"(\d+)\s+(minute|minutes|hour|hours|day|days)\s+ago", text.casefold())
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        return reference - timedelta(**({"minutes": amount} if unit.startswith("minute") else {"hours": amount} if unit.startswith("hour") else {"days": amount}))
    if text.casefold() == "yesterday":
        return reference - timedelta(days=1)
    formats = ["%b %d, %Y", "%B %d, %Y"]
    if re.fullmatch(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}", text, re.I):
        formats.extend(("%b %d", "%B %d"))
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt).replace(tzinfo=reference.tzinfo)
            return parsed.replace(year=reference.year) if "%Y" not in fmt else parsed
        except ValueError:
            continue
    return None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class _DateMarkupParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.json_ld: str | None = None
        self.meta: str | None = None
        self.time: str | None = None
        self.source_specific: str | None = None
        self.visible: str | None = None
        self.relative: str | None = None
        self._script = False
        self._json_buffer: list[str] = []
        self._visible_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and attributes.get("type") == "application/ld+json":
            self._script = True
            self._json_buffer = []
        if tag == "meta":
            key = attributes.get("property") or attributes.get("name")
            if key and key.casefold() in {"article:published_time", "date", "pubdate", "datepublished"}:
                self.meta = attributes.get("content")
        if tag == "time":
            self.time = attributes.get("datetime")

    def handle_data(self, data: str) -> None:
        if self._script:
            self._json_buffer.append(data)
        elif data.strip():
            if re.search(r"\b\d+\s+(minutes?|hours?|days?)\s+ago\b", data, re.I):
                self.relative = data.strip()
            else:
                self._visible_parts.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._script:
            self._script = False
            text = "".join(self._json_buffer)
            match = re.search(r'"(?:datePublished|dateCreated|published_at)"\s*:\s*"([^"]+)"', text)
            if match:
                self.json_ld = match.group(1)
        self.visible = " ".join(self._visible_parts) or None
