from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.freshness.dedupe import DedupeIndex, RedisDedupeIndex
from src.freshness.policies import evaluate_freshness, select_date
from src.freshness.watermark import WatermarkStore

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


def test_date_priority_prefers_json_ld_over_lower_priority_sources() -> None:
    html = '''<script type="application/ld+json">{"datePublished":"2026-09-11T11:00:00Z"}</script><meta property="article:published_time" content="2026-09-10T11:00:00Z"><time datetime="2026-09-09T11:00:00Z"></time>'''
    evidence = select_date(html=html, rss_date="Wed, 08 Sep 2026 11:00:00 GMT", now=NOW)
    assert evidence.source == "json_ld"
    assert evidence.published_at == datetime(2026, 9, 11, 11, tzinfo=UTC)


def test_freshness_rejects_stale_and_future_and_quarantines_unknown() -> None:
    stale = evaluate_freshness(select_date(rss_date=NOW - timedelta(hours=25), now=NOW), now=NOW)
    future = evaluate_freshness(select_date(rss_date=NOW + timedelta(minutes=1), now=NOW), now=NOW)
    unknown = evaluate_freshness(select_date(html="<html>No date</html>", now=NOW), now=NOW)
    assert stale.status == "REJECT" and stale.reason == "stale_date"
    assert future.status == "REJECT" and future.reason == "future_date"
    assert unknown.status == "QUARANTINE"


def test_relative_dates_are_low_confidence_and_quarantined() -> None:
    evidence = select_date(html="<time>2 hours ago</time>", now=NOW)
    decision = evaluate_freshness(evidence, now=NOW)
    assert evidence.source == "relative"
    assert decision.status == "QUARANTINE"


def test_dedupe_tracks_url_and_normalized_content() -> None:
    index = DedupeIndex()
    assert index.check_and_add("news", "https://example.com/story?utm_source=x", "Same story")
    assert not index.check_and_add("news", "https://example.com/story", "Different text")
    assert not index.check_and_add("news", "https://example.com/other", " same   STORY ")


def test_dedupe_can_reload_persistent_identity_layers(tmp_path: Path) -> None:
    path = tmp_path / "dedupe.json"
    index = DedupeIndex(path=path)
    assert index.check_and_add("news", "https://example.com/story", "Same story")
    restored = DedupeIndex(path=path)
    assert not restored.check_and_add("news", "https://example.com/story", "Different text")


async def test_redis_dedupe_claims_url_and_content_atomically() -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int, str, str]] = []
            self.claimed = False

        async def eval(self, script: str, key_count: int, url_key: str, hash_key: str) -> int:
            self.calls.append((script, key_count, url_key, hash_key))
            if self.claimed:
                return 0
            self.claimed = True
            return 1

    redis = FakeRedis()
    index = RedisDedupeIndex("redis://unused", client=redis)
    assert await index.check_and_add("news", "https://example.com/story", "Same story")
    assert not await index.check_and_add("news", "https://example.com/story", "Different text")
    assert redis.calls[0][1] == 2
    assert ":url:" in redis.calls[0][2]
    assert ":content:" in redis.calls[0][3]


def test_watermark_persists_highest_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "watermarks.json"
    store = WatermarkStore(path)
    store.advance("news", NOW)
    store.advance("news", NOW - timedelta(hours=1))
    restored = WatermarkStore(path)
    assert restored.get("news") == NOW
