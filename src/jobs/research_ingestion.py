"""Evidence-first research ingestion, including PWC and verified GitHub enrichment."""

from __future__ import annotations

from dataclasses import dataclass, replace

from src.crawlers.base import SourceAdapter
from src.crawlers.research.arxiv import ArxivMetadataClient
from src.crawlers.research.github import GitHubClient
from src.crawlers.research.models import ResearchPaperCandidate
from src.fetch.retry import RetryableFailure
from src.observability.logging import log_event
from src.parsing.identity import deterministic_record_id
from src.schemas.common import Provenance, SourceReference
from src.schemas.research import ResearchPaperContent, ResearchPaperRecord
from src.storage.base import ResearchPaperRepository
from src.storage.object_store import LocalRawStore, RawDocument


class CandidateRejectedError(ValueError):
    """A record is unsupported by sufficient source evidence and must not be persisted."""


@dataclass(frozen=True, slots=True)
class IngestionSummary:
    discovered_urls: int
    parsed_records: int
    inserted_records: int
    duplicates_prevented: int
    rejected_records: int


class ResearchIngestionJob:
    """Persist every raw input before deterministic enrichment and validation."""

    def __init__(
        self,
        *,
        adapter: SourceAdapter[ResearchPaperCandidate],
        raw_store: LocalRawStore,
        repository: ResearchPaperRepository,
        arxiv_metadata_client: ArxivMetadataClient | None = None,
        github_client: GitHubClient | None = None,
    ) -> None:
        self._adapter = adapter
        self._raw_store = raw_store
        self._repository = repository
        self._arxiv_metadata_client = arxiv_metadata_client
        self._github_client = github_client

    async def run(self) -> IngestionSummary:
        discovered_urls = await self._adapter.discover()
        parsed_count = inserted_count = duplicate_count = rejected_count = 0

        for url in discovered_urls:
            response = await self._adapter.fetch(url)
            primary_raw_document = await self._raw_store.put(self._adapter.source_id, response)
            candidates = self._adapter.parse(response)
            for candidate in candidates:
                parsed_count += 1
                try:
                    record, raw_documents = await self._prepare_record(candidate, primary_raw_document)
                except CandidateRejectedError as exc:
                    rejected_count += 1
                    log_event(
                        "research_record_rejected",
                        source_id=self._adapter.source_id,
                        canonical_url=candidate.canonical_url,
                        reason=str(exc),
                    )
                    continue
                result = await self._repository.upsert(
                    record,
                    raw_documents,
                    source_id=self._adapter.source_id,
                )
                inserted_count += int(result.inserted)
                duplicate_count += int(result.duplicate_prevented)
                log_event(
                    "research_record_persisted",
                    source_id=self._adapter.source_id,
                    record_id=record.record_id,
                    canonical_url=str(record.source.canonical_url),
                    raw_document_id=record.provenance.raw_document_id,
                    status="inserted" if result.inserted else "duplicate_prevented",
                )

        return IngestionSummary(
            discovered_urls=len(discovered_urls),
            parsed_records=parsed_count,
            inserted_records=inserted_count,
            duplicates_prevented=duplicate_count,
            rejected_records=rejected_count,
        )

    async def _prepare_record(
        self,
        candidate: ResearchPaperCandidate,
        primary_raw_document: RawDocument,
    ) -> tuple[ResearchPaperRecord, list[RawDocument]]:
        raw_documents = [primary_raw_document]
        candidate = await self._hydrate_bibliography(candidate, raw_documents)
        candidate = await self._enrich_github(candidate, raw_documents)
        return _build_record(candidate, primary_raw_document, raw_documents), raw_documents

    async def _hydrate_bibliography(
        self,
        candidate: ResearchPaperCandidate,
        raw_documents: list[RawDocument],
    ) -> ResearchPaperCandidate:
        if not candidate.needs_bibliographic_hydration:
            return candidate
        arxiv_id = candidate.source_metadata.get("paper_arxiv_id")
        if not isinstance(arxiv_id, str) or not arxiv_id:
            raise CandidateRejectedError("PWC record lacks an arXiv identifier for required metadata")
        if self._arxiv_metadata_client is None:
            raise CandidateRejectedError("No arXiv metadata client is configured for this incomplete record")
        try:
            arxiv_candidate, response = await self._arxiv_metadata_client.fetch_by_id(arxiv_id)
        except (RetryableFailure, RuntimeError, ValueError) as exc:
            raise CandidateRejectedError(f"Could not verify bibliographic metadata from arXiv: {exc}") from exc
        if arxiv_candidate.paper_url != candidate.paper_url:
            raise CandidateRejectedError("PWC and arXiv evidence identify different papers")
        arxiv_raw_document = await self._raw_store.put("arxiv", response)
        raw_documents.append(arxiv_raw_document)
        return replace(
            candidate,
            title=arxiv_candidate.title,
            authors=arxiv_candidate.authors,
            published_at=arxiv_candidate.published_at,
            abstract=arxiv_candidate.abstract,
            source_metadata={
                **candidate.source_metadata,
                "bibliographic_parser": "arxiv_atom_v1",
                "bibliographic_source_url": arxiv_candidate.original_url,
                "bibliographic_raw_document_id": arxiv_raw_document.raw_document_id,
            },
        )

    async def _enrich_github(
        self,
        candidate: ResearchPaperCandidate,
        raw_documents: list[RawDocument],
    ) -> ResearchPaperCandidate:
        if candidate.github_url is None:
            return candidate
        if self._github_client is None:
            raise CandidateRejectedError("No GitHub client is configured for a code-linked paper")
        try:
            repository = await self._github_client.get_repository(candidate.github_url)
        except (RetryableFailure, RuntimeError, ValueError) as exc:
            raise CandidateRejectedError(f"Could not verify GitHub repository metadata: {exc}") from exc
        github_raw_document = await self._raw_store.put("github", repository.raw_response)
        raw_documents.append(github_raw_document)
        return replace(
            candidate,
            github_url=repository.normalized_url,
            source_metadata={
                **candidate.source_metadata,
                "github_api_full_name": repository.full_name,
                "github_api_raw_document_id": github_raw_document.raw_document_id,
                "github_api_retrieved_at": repository.fetched_at.isoformat(),
                "github_stars": repository.stars,
            },
        )


def _build_record(
    candidate: ResearchPaperCandidate,
    primary_raw_document: RawDocument,
    raw_documents: list[RawDocument],
) -> ResearchPaperRecord:
    if candidate.published_at is None:
        raise CandidateRejectedError("Research paper has no verified published date")
    github_stars = candidate.source_metadata.get("github_stars")
    if candidate.github_url is not None and not isinstance(github_stars, int):
        raise CandidateRejectedError("Research paper has a GitHub URL without verified GitHub stars")
    record_id = deterministic_record_id(primary_raw_document.source_id, candidate.canonical_url)
    return ResearchPaperRecord(
        recordId=record_id,
        schemaVersion="1.0",
        recordType="RESEARCH_PAPER",
        source=SourceReference(
            name=_source_name(primary_raw_document.source_id),
            url=candidate.original_url,
            canonicalUrl=candidate.canonical_url,
        ),
        collectedAt=primary_raw_document.retrieved_at,
        provenance=Provenance(
            retrievedAt=primary_raw_document.retrieved_at,
            contentHash=primary_raw_document.content_hash,
            rawDocumentId=primary_raw_document.raw_document_id,
            extractionMethod="deterministic",
            extractionMetadata={
                **candidate.source_metadata,
                "raw_document_ids": [document.raw_document_id for document in raw_documents],
                "llm_used": False,
            },
            validationStatus="VALID",
        ),
        content=ResearchPaperContent(
            title=candidate.title,
            authors=candidate.authors,
            paper_url=candidate.paper_url,
            github_url=candidate.github_url,
            github_stars=github_stars if isinstance(github_stars, int) else None,
            published_date=candidate.published_at,
            abstract=candidate.abstract,
        ),
    )


def _source_name(source_id: str) -> str:
    return {"arxiv": "arXiv", "papers_with_code": "Papers with Code archive"}.get(
        source_id, source_id
    )
