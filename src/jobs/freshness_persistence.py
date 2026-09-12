"""Validated persistence sink for accepted fresh news and job candidates."""

from __future__ import annotations

from typing import Protocol

from src.crawlers.jobs.base import JobCandidate
from src.crawlers.news.base import NewsCandidate
from src.freshness.policies import FreshnessDecision
from src.parsing.identity import deterministic_record_id
from src.schemas.common import Provenance, SourceReference
from src.schemas.job import JobContent, JobRecord
from src.schemas.news import NewsContent, NewsFreshness, NewsRecord
from src.storage.base import PersistenceResult
from src.storage.object_store import RawDocument


class FreshnessRepository(Protocol):
    async def upsert_news(
        self, record: NewsRecord, raw_document: RawDocument, *, source_id: str
    ) -> PersistenceResult:
        ...

    async def upsert_job(
        self, record: JobRecord, raw_document: RawDocument, *, source_id: str
    ) -> PersistenceResult:
        ...


class FreshnessPersistenceSink:
    """Convert only policy-accepted candidates into provenance-bearing records."""

    def __init__(self, repository: FreshnessRepository) -> None:
        self._repository = repository

    async def persist(
        self,
        source_id: str,
        candidate: NewsCandidate | JobCandidate,
        decision: FreshnessDecision,
        raw_document: RawDocument,
    ) -> PersistenceResult:
        if decision.status != "ACCEPT" or decision.published_at is None:
            raise ValueError("Only accepted candidates with a resolved date may be persisted")
        if isinstance(candidate, NewsCandidate):
            record = _news_record(source_id, candidate, decision, raw_document)
            return await self._repository.upsert_news(record, raw_document, source_id=source_id)
        record = _job_record(source_id, candidate, decision, raw_document)
        return await self._repository.upsert_job(record, raw_document, source_id=source_id)


def _provenance(raw_document: RawDocument, candidate: NewsCandidate | JobCandidate) -> Provenance:
    return Provenance(
        retrievedAt=raw_document.retrieved_at,
        contentHash=raw_document.content_hash,
        rawDocumentId=raw_document.raw_document_id,
        extractionMethod="deterministic",
        extractionMetadata={
            "raw_document_ids": [raw_document.raw_document_id],
            "date_source": candidate.date_source,
            "date_confidence": candidate.date_confidence,
            "llm_used": False,
        },
        validationStatus="VALID",
    )


def _source(raw_document: RawDocument, candidate: NewsCandidate | JobCandidate) -> SourceReference:
    return SourceReference(
        name=raw_document.source_id,
        url=candidate.original_url,
        canonicalUrl=candidate.canonical_url,
    )


def _news_record(
    source_id: str,
    candidate: NewsCandidate,
    decision: FreshnessDecision,
    raw_document: RawDocument,
) -> NewsRecord:
    assert decision.published_at is not None
    return NewsRecord(
        recordId=deterministic_record_id(source_id, candidate.canonical_url),
        schemaVersion="1.0",
        recordType="NEWS",
        source=_source(raw_document, candidate),
        collectedAt=raw_document.retrieved_at,
        provenance=_provenance(raw_document, candidate),
        content=NewsContent(
            title=candidate.title,
            publishedDate=decision.published_at,
            author=candidate.author,
            body=candidate.body,
            category=candidate.category,
        ),
        freshness=NewsFreshness(
            ageHours=max(0.0, decision.age_hours or 0.0),
            dateSource=decision.source,
            dateConfidence=decision.confidence,
            isFresh=True,
        ),
    )


def _job_record(
    source_id: str,
    candidate: JobCandidate,
    decision: FreshnessDecision,
    raw_document: RawDocument,
) -> JobRecord:
    assert decision.published_at is not None
    return JobRecord(
        recordId=deterministic_record_id(source_id, candidate.canonical_url),
        schemaVersion="1.0",
        recordType="JOB",
        source=_source(raw_document, candidate),
        collectedAt=raw_document.retrieved_at,
        provenance=_provenance(raw_document, candidate),
        content=JobContent(
            company=candidate.company,
            date=decision.published_at,
            isRemote=candidate.is_remote,
            roleFamily=candidate.role_family,
            title=candidate.title,
            description=candidate.description,
        ),
    )