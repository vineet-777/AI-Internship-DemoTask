"""Freshness-gated ingestion orchestration for news and jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from src.crawlers.jobs.base import JobCandidate
from src.crawlers.news.base import NewsCandidate
from src.crawlers.base import SourceAdapter
from src.fetch.retry import RetryableFailure
from src.freshness.dedupe import DedupeIndex
from src.freshness.policies import FreshnessDecision, evaluate_freshness
from src.freshness.watermark import WatermarkStore

Candidate = NewsCandidate | JobCandidate


class CandidateSink(Protocol):
    async def persist(self, source_id: str, candidate: Candidate, decision: FreshnessDecision) -> None:
        ...


@dataclass(frozen=True, slots=True)
class FreshnessSummary:
    discovered_urls: int
    parsed_records: int
    accepted_records: int
    rejected_records: int
    quarantined_records: int
    duplicates_prevented: int
    reasons: dict[str, int] = field(default_factory=dict)


class FreshnessIngestionJob:
    """Apply the hard freshness gate before optional persistence."""

    def __init__(
        self,
        *,
        adapter: SourceAdapter[Candidate],
        watermark_store: WatermarkStore,
        dedupe_index: DedupeIndex | None = None,
        sink: CandidateSink | None = None,
        now_factory: callable = lambda: datetime.now(UTC),
    ) -> None:
        self._adapter = adapter
        self._watermarks = watermark_store
        self._dedupe = dedupe_index or DedupeIndex()
        self._sink = sink
        self._now_factory = now_factory

    async def run(self) -> FreshnessSummary:
        discovered = await self._adapter.discover()
        accepted = rejected = quarantined = duplicates = parsed = 0
        reasons: dict[str, int] = {}
        for url in discovered:
            try:
                response = await self._adapter.fetch(url)
                candidates = self._adapter.parse(response)
            except (RetryableFailure, RuntimeError, ValueError):
                reasons["source_failure"] = reasons.get("source_failure", 0) + 1
                continue
            for candidate in candidates:
                parsed += 1
                decision = evaluate_freshness(
                    _candidate_evidence(candidate),
                    now=self._now_factory(),
                )
                reasons[decision.reason] = reasons.get(decision.reason, 0) + 1
                if decision.status == "QUARANTINE":
                    quarantined += 1
                    continue
                if decision.status != "ACCEPT":
                    rejected += 1
                    continue
                if not self._dedupe.check_and_add(self._adapter.source_id, candidate.canonical_url, _candidate_content(candidate)):
                    duplicates += 1
                    continue
                accepted += 1
                if decision.published_at is not None:
                    self._watermarks.advance(self._adapter.source_id, decision.published_at)
                if self._sink is not None:
                    await self._sink.persist(self._adapter.source_id, candidate, decision)
        return FreshnessSummary(len(discovered), parsed, accepted, rejected, quarantined, duplicates, reasons)


def _candidate_evidence(candidate: Candidate):
    from src.freshness.policies import DateEvidence

    return DateEvidence(candidate.published_at, candidate.date_source, candidate.date_confidence)


def _candidate_content(candidate: Candidate) -> str:
    if isinstance(candidate, NewsCandidate):
        return f"{candidate.title}\n{candidate.body}"
    return f"{candidate.title}\n{candidate.description}\n{candidate.company}"
