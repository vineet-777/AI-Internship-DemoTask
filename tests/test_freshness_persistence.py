from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.crawlers.jobs.base import JobCandidate
from src.crawlers.news.base import NewsCandidate
from src.freshness.policies import FreshnessDecision
from src.jobs.freshness_persistence import FreshnessPersistenceSink
from src.schemas.job import JobRecord
from src.schemas.news import NewsRecord
from src.storage.base import PersistenceResult
from src.storage.object_store import RawDocument


NOW = datetime(2026, 9, 12, 12, tzinfo=UTC)


class RecordingRepository:
    def __init__(self) -> None:
        self.news: list[NewsRecord] = []
        self.jobs: list[JobRecord] = []

    async def upsert_news(self, record: NewsRecord, raw_document: RawDocument, *, source_id: str) -> PersistenceResult:
        self.news.append(record)
        return PersistenceResult(record.record_id, True)

    async def upsert_job(self, record: JobRecord, raw_document: RawDocument, *, source_id: str) -> PersistenceResult:
        self.jobs.append(record)
        return PersistenceResult(record.record_id, True)


def _raw_document() -> RawDocument:
    return RawDocument(
        raw_document_id="raw-1",
        source_id="techcrunch_ai",
        original_url="https://techcrunch.com/feed",
        canonical_url="https://techcrunch.com/feed",
        content_hash="a" * 64,
        retrieved_at=NOW,
        status_code=200,
        headers={"content-type": "application/rss+xml"},
        storage_key="techcrunch_ai/2026/09/12/a.xml",
        content_type="application/rss+xml",
    )


def test_freshness_sink_builds_provenance_bearing_news_and_job_records() -> None:
    repository = RecordingRepository()
    sink = FreshnessPersistenceSink(repository)
    decision = FreshnessDecision("ACCEPT", NOW - timedelta(hours=2), "rss", 0.85, 2.0, "fresh")
    raw_document = _raw_document()

    async def persist() -> None:
        await sink.persist(
            "techcrunch_ai",
            NewsCandidate(
                "https://techcrunch.com/story",
                "https://techcrunch.com/story",
                "AI launch",
                "Details",
                "Acme",
                NOW - timedelta(hours=2),
                "rss",
                0.85,
            ),
            decision,
            raw_document,
        )
        await sink.persist(
            "remoteok_ai",
            JobCandidate(
                "https://remoteok.com/job",
                "https://remoteok.com/job",
                "Acme",
                "AI Engineer",
                "Build systems",
                NOW - timedelta(hours=2),
                "rss",
                0.85,
                True,
                "Engineering",
            ),
            decision,
            raw_document,
        )

    import asyncio

    asyncio.run(persist())

    assert repository.news[0].content.title == "AI launch"
    assert repository.news[0].freshness.is_fresh is True
    assert repository.news[0].provenance.raw_document_id == "raw-1"
    assert repository.jobs[0].content.is_remote is True
    assert repository.jobs[0].content.role_family == "Engineering"


@pytest.mark.asyncio
async def test_freshness_sink_rejects_non_accepted_candidates() -> None:
    sink = FreshnessPersistenceSink(RecordingRepository())
    decision = FreshnessDecision("QUARANTINE", None, None, 0.0, None, "date_unresolved")
    with pytest.raises(ValueError, match="Only accepted"):
        await sink.persist(
            "news",
            NewsCandidate("https://example.com/a", "https://example.com/a", "Title", "Body", None, None, None, 0.0),
            decision,
            _raw_document(),
        )