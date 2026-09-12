"""Local file and memory repository fallback for offline and local runs."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from src.export.sheets import REQUIRED_TABS
from src.schemas.job import JobRecord
from src.schemas.news import NewsRecord
from src.schemas.product import ProductRecord
from src.schemas.research import ResearchPaperRecord
from src.schemas.startup import StartupRecord
from src.storage.base import PersistenceResult
from src.storage.object_store import RawDocument


class LocalIntelligenceRepository:
    """Stores validated records locally in memory and persistent JSONL files."""

    def __init__(self, data_root: Path | str = "data/normalized") -> None:
        self._data_root = Path(data_root)
        self._data_root.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, dict[str, Any]] = {tab: {} for tab in REQUIRED_TABS}

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def __aenter__(self) -> "LocalIntelligenceRepository":
        return self

    async def __aexit__(self, *_: object) -> None:
        pass

    async def upsert(
        self,
        record: Any,
        raw_documents: Sequence[RawDocument],
        *,
        source_id: str,
    ) -> PersistenceResult:
        if isinstance(record, StartupRecord):
            return await self.upsert_startup(record, raw_documents, source_id=source_id)
        if isinstance(record, ProductRecord):
            return await self.upsert_product(record, raw_documents, source_id=source_id)
        # Research paper
        tab = "Research Papers"
        rec_id = record.record_id
        is_new = rec_id not in self._records[tab]
        if is_new:
            payload = record.model_dump(mode="json", by_alias=True)
            self._records[tab][rec_id] = payload
            self._append_to_disk("research_papers.jsonl", payload)
        return PersistenceResult(record_id=rec_id, inserted=is_new)

    async def upsert_startup(
        self,
        record: StartupRecord,
        raw_documents: Sequence[RawDocument],
        *,
        source_id: str,
    ) -> PersistenceResult:
        tab = "Startups"
        rec_id = record.record_id
        is_new = rec_id not in self._records[tab]
        if is_new:
            payload = record.model_dump(mode="json", by_alias=True)
            self._records[tab][rec_id] = payload
            self._append_to_disk("startups.jsonl", payload)
        return PersistenceResult(record_id=rec_id, inserted=is_new)

    async def upsert_product(
        self,
        record: ProductRecord,
        raw_documents: Sequence[RawDocument],
        *,
        source_id: str,
    ) -> PersistenceResult:
        tab = "Products"
        rec_id = record.record_id
        is_new = rec_id not in self._records[tab]
        if is_new:
            payload = record.model_dump(mode="json", by_alias=True)
            self._records[tab][rec_id] = payload
            self._append_to_disk("products.jsonl", payload)
        return PersistenceResult(record_id=rec_id, inserted=is_new)

    async def upsert_news(
        self,
        record: NewsRecord,
        raw_document: RawDocument,
        *,
        source_id: str,
    ) -> PersistenceResult:
        tab = "News"
        rec_id = record.record_id
        is_new = rec_id not in self._records[tab]
        if is_new:
            payload = record.model_dump(mode="json", by_alias=True)
            self._records[tab][rec_id] = payload
            self._append_to_disk("news.jsonl", payload)
        return PersistenceResult(record_id=rec_id, inserted=is_new)

    async def upsert_job(
        self,
        record: JobRecord,
        raw_document: RawDocument,
        *,
        source_id: str,
    ) -> PersistenceResult:
        tab = "Jobs"
        rec_id = record.record_id
        is_new = rec_id not in self._records[tab]
        if is_new:
            payload = record.model_dump(mode="json", by_alias=True)
            self._records[tab][rec_id] = payload
            self._append_to_disk("jobs.jsonl", payload)
        return PersistenceResult(record_id=rec_id, inserted=is_new)

    async def upsert_mapping(
        self,
        *,
        raw_name: str,
        canonical_name: str | None,
        source: str,
        method: str,
        confidence: float,
        status: str,
        record_id: str | None = None,
    ) -> None:
        tab = "Entity Mapping Log"
        entry = {
            "rawName": raw_name,
            "canonicalName": canonical_name,
            "source": source,
            "method": method,
            "confidence": confidence,
            "status": status,
            "recordId": record_id,
        }
        key = f"{raw_name}:{source}"
        self._records[tab][key] = entry
        self._append_to_disk("entity_mapping_log.jsonl", entry)

    def read_tabs(self) -> dict[str, list[object]]:
        # Read from memory or backfill from JSONL files if empty
        result: dict[str, list[object]] = {}
        file_map = {
            "Startups": "startups.jsonl",
            "Products": "products.jsonl",
            "Research Papers": "research_papers.jsonl",
            "Jobs": "jobs.jsonl",
            "News": "news.jsonl",
            "Entity Mapping Log": "entity_mapping_log.jsonl",
        }
        for tab in REQUIRED_TABS:
            items = list(self._records[tab].values())
            if not items:
                filepath = self._data_root / file_map[tab]
                if filepath.exists():
                    for line in filepath.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            try:
                                items.append(json.loads(line))
                            except Exception:
                                pass
            result[tab] = items
        return result

    def _append_to_disk(self, filename: str, item: dict[str, Any]) -> None:
        target = self._data_root / filename
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
