from __future__ import annotations

from datetime import UTC, datetime

from src.crawlers.feeds import parse_feed
from src.fetch.http_client import RawResponse


def test_rss_feed_parser_preserves_date_evidence() -> None:
    response = RawResponse(
        request_url="https://example.com/feed.xml",
        response_url="https://example.com/feed.xml",
        status_code=200,
        headers={"content-type": "application/rss+xml"},
        body=b'''<rss><channel><item><title>AI launch</title><link>https://example.com/story</link><description>Details</description><pubDate>Fri, 11 Sep 2026 11:00:00 GMT</pubDate><author>Acme</author></item></channel></rss>''',
        retrieved_at=datetime(2026, 9, 11, 12, tzinfo=UTC),
        attempts=1,
    )
    items = parse_feed(response)
    assert len(items) == 1
    assert items[0].date_source == "rss"
    assert items[0].author == "Acme"
