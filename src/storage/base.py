"""Storage contracts which keep pipeline orchestration backend independent."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence
from typing import Protocol

from src.schemas.product import ProductRecord
from src.schemas.job import JobRecord
from src.schemas.news import NewsRecord
from src.schemas.research import ResearchPaperRecord
from src.schemas.startup import StartupRecord
from src.storage.object_store import RawDocument


@dataclass(frozen=True, slots=True)
class PersistenceResult:
    record_id: str
    inserted: bool

    @property
    def duplicate_prevented(self) -> bool:
        return not self.inserted


class ResearchPaperRepository(Protocol):
    async def upsert(
        self,
        record: ResearchPaperRecord,
        raw_documents: Sequence[RawDocument],
        *,
        source_id: str,
    ) -> PersistenceResult:
        """Persist one validated record and its raw-evidence linkage atomically."""


class StartupRepository(Protocol):
    async def upsert(
        self,
        record: StartupRecord,
        raw_documents: Sequence[RawDocument],
        *,
        source_id: str,
    ) -> PersistenceResult:
        """Persist one validated startup record and its raw-evidence linkage atomically."""


class ProductRepository(Protocol):
    async def upsert(
        self,
        record: ProductRecord,
        raw_documents: Sequence[RawDocument],
        *,
        source_id: str,
    ) -> PersistenceResult:
        """Persist one validated product record and its raw-evidence linkage atomically."""


class FreshnessRepository(Protocol):
    async def upsert_news(
        self, record: NewsRecord, raw_document: RawDocument, *, source_id: str
    ) -> PersistenceResult:
        """Persist one accepted fresh news record atomically."""

    async def upsert_job(
        self, record: JobRecord, raw_document: RawDocument, *, source_id: str
    ) -> PersistenceResult:
        """Persist one accepted fresh job record atomically."""
