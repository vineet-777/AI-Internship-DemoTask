"""Evidence-first product ingestion for Product Hunt and related product directories."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.crawlers.base import SourceAdapter
from src.crawlers.product.base import ProductCandidate
from src.entities.mapping_store import MappingStore
from src.entities.matcher import EntityMatcher, MatchStatus
from src.parsing.identity import deterministic_record_id
from src.schemas.common import Provenance, SourceReference
from src.schemas.product import ProductContent, ProductRecord
from src.storage.base import ProductRepository
from src.storage.object_store import LocalRawStore, RawDocument

if TYPE_CHECKING:
    from src.extraction.orchestrator import LLMOrchestrator

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProductIngestionSummary:
    discovered_urls: int
    parsed_records: int
    inserted_records: int
    duplicates_prevented: int
    rejected_records: int


class ProductIngestionJob:
    """Persist product records only after raw evidence is safely stored."""

    def __init__(
        self,
        *,
        adapter: SourceAdapter[ProductCandidate],
        raw_store: LocalRawStore,
        repository: ProductRepository,
        entity_matcher: EntityMatcher | None = None,
        mapping_store: MappingStore | None = None,
        llm_orchestrator: LLMOrchestrator | None = None,
    ) -> None:
        self._adapter = adapter
        self._raw_store = raw_store
        self._repository = repository
        self._entity_matcher = entity_matcher
        self._mapping_store = mapping_store
        self._llm_orchestrator = llm_orchestrator

    async def run(self) -> ProductIngestionSummary:
        discovered_urls = await self._adapter.discover()
        parsed_records = inserted_records = duplicates_prevented = rejected_records = 0

        for url in discovered_urls:
            response = await self._adapter.fetch(url)
            primary_raw_document = await self._raw_store.put(self._adapter.source_id, response)
            candidates = self._adapter.parse(response)
            for candidate in candidates:
                parsed_records += 1
                # LLM enrichment layer
                llm_used = False
                if self._llm_orchestrator is not None:
                    from src.extraction.pipeline_extractor import enrich_product_with_llm
                    candidate, llm_used = await enrich_product_with_llm(self._llm_orchestrator, candidate)
                try:
                    record, raw_documents = self._prepare_record(candidate, primary_raw_document, llm_used=llm_used)
                except ValueError:
                    rejected_records += 1
                    continue
                result = await self._repository.upsert(
                    record,
                    raw_documents,
                    source_id=self._adapter.source_id,
                )
                self._append_mapping(candidate.startup_name, record.record_id)
                inserted_records += int(result.inserted)
                duplicates_prevented += int(result.duplicate_prevented)

        return ProductIngestionSummary(
            discovered_urls=len(discovered_urls),
            parsed_records=parsed_records,
            inserted_records=inserted_records,
            duplicates_prevented=duplicates_prevented,
            rejected_records=rejected_records,
        )

    def _prepare_record(
        self,
        candidate: ProductCandidate,
        primary_raw_document: RawDocument,
        *,
        llm_used: bool = False,
    ) -> tuple[ProductRecord, list[RawDocument]]:
        raw_documents = [primary_raw_document]
        candidate = self._resolve_candidate(candidate)
        record = _build_record(candidate, primary_raw_document, raw_documents, llm_used=llm_used)
        return record, raw_documents

    def _resolve_candidate(self, candidate: ProductCandidate) -> ProductCandidate:
        if self._entity_matcher is None:
            return candidate
        match = self._entity_matcher.match(candidate.startup_name)
        data = candidate.data.copy()
        data["rawStartupName"] = candidate.startup_name
        data["resolutionConfidence"] = match.confidence
        if match.canonical_entity_id is not None:
            data["canonicalEntityId"] = match.canonical_entity_id
        startup_name = (
            match.canonical_name
            if match.status == MatchStatus.AUTO_MATCH and match.canonical_name
            else candidate.startup_name
        )
        return ProductCandidate(
            candidate.original_url,
            candidate.canonical_url,
            candidate.product_name,
            startup_name,
            candidate.pricing_model,
            data,
        )

    def _append_mapping(self, raw_name: str, record_id: str) -> None:
        if self._entity_matcher is not None and self._mapping_store is not None:
            self._mapping_store.append(
                self._entity_matcher.match(raw_name),
                source=self._adapter.source_id,
                record_id=record_id,
            )


def _build_record(
    candidate: ProductCandidate,
    primary_raw_document: RawDocument,
    raw_documents: list[RawDocument],
    *,
    llm_used: bool = False,
) -> ProductRecord:
    record_id = deterministic_record_id(primary_raw_document.source_id, candidate.canonical_url)
    payload = candidate.data.copy()
    payload.setdefault("rawStartupName", candidate.startup_name)
    return ProductRecord(
        recordId=record_id,
        schemaVersion="1.0",
        recordType="PRODUCT",
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
            extractionMethod="llm_augmented" if llm_used else "deterministic",
            extractionMetadata={
                "raw_document_ids": [document.raw_document_id for document in raw_documents],
                "llm_used": llm_used,
            },
            validationStatus="VALID",
        ),
        content=ProductContent(
            productName=candidate.product_name,
            startupName=candidate.startup_name,
            pricingModel=candidate.pricing_model,
            **payload,
        ),
    )


def _source_name(source_id: str) -> str:
    return {"product_hunt": "Product Hunt"}.get(source_id, source_id)