"""Storage contracts which keep pipeline orchestration backend independent."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence
from typing import Protocol

from src.schemas.research import ResearchPaperRecord
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
