"""PostgreSQL repository with database-enforced idempotency."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from src.schemas.research import ResearchPaperRecord
from src.storage.base import PersistenceResult
from src.storage.object_store import RawDocument

if TYPE_CHECKING:
    import asyncpg


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS raw_documents (
    raw_document_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    original_url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    storage_key TEXT NOT NULL,
    metadata JSONB NOT NULL,
    UNIQUE (source_id, canonical_url, content_hash)
);

CREATE TABLE IF NOT EXISTS research_papers (
    record_id CHAR(64) PRIMARY KEY,
    source_id TEXT NOT NULL,
    original_url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    title TEXT NOT NULL,
    authors JSONB NOT NULL,
    paper_url TEXT NOT NULL,
    github_url TEXT,
    github_stars INTEGER,
    published_at TIMESTAMPTZ NOT NULL,
    raw_document_id TEXT NOT NULL REFERENCES raw_documents(raw_document_id),
    content_hash CHAR(64) NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    record_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_id, canonical_url)
);

CREATE INDEX IF NOT EXISTS research_papers_published_at_idx ON research_papers (published_at);
CREATE INDEX IF NOT EXISTS research_papers_raw_document_id_idx ON research_papers (raw_document_id);
"""


class PostgresResearchRepository:
    """System-of-record persistence for validated research-paper records."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._pool: Any | None = None

    async def open(self) -> None:
        try:
            import asyncpg
        except ImportError as exc:  # pragma: no cover - installation failure is environmental
            raise RuntimeError("Install project dependencies before using PostgreSQL persistence") from exc
        self._pool = await asyncpg.create_pool(self._database_url, min_size=1, max_size=5)
        async with self._pool.acquire() as connection:
            await connection.execute(SCHEMA_SQL)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def __aenter__(self) -> "PostgresResearchRepository":
        await self.open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def upsert(
        self,
        record: ResearchPaperRecord,
        raw_documents: Sequence[RawDocument],
        *,
        source_id: str,
    ) -> PersistenceResult:
        if self._pool is None:
            raise RuntimeError("PostgresResearchRepository.open() must be called before upsert()")

        if not raw_documents:
            raise ValueError("At least one raw document is required for a canonical record")
        if record.provenance.raw_document_id not in {
            document.raw_document_id for document in raw_documents
        }:
            raise ValueError("The record's primary raw document must be included in raw_documents")

        async with self._pool.acquire() as connection:
            async with connection.transaction():
                for raw_document in raw_documents:
                    await connection.execute(
                        """
                        INSERT INTO raw_documents (
                            raw_document_id, source_id, original_url, canonical_url, content_hash,
                            retrieved_at, storage_key, metadata
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
                        ON CONFLICT (raw_document_id) DO NOTHING
                        """,
                        raw_document.raw_document_id,
                        raw_document.source_id,
                        raw_document.original_url,
                        raw_document.canonical_url,
                        raw_document.content_hash,
                        raw_document.retrieved_at,
                        raw_document.storage_key,
                        json.dumps(_raw_metadata(raw_document)),
                    )
                inserted_id = await connection.fetchval(
                    """
                    INSERT INTO research_papers (
                        record_id, source_id, original_url, canonical_url, title, authors,
                        paper_url, github_url, github_stars, published_at, raw_document_id,
                        content_hash, retrieved_at, record_payload
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11, $12, $13, $14::jsonb
                    )
                    ON CONFLICT (record_id) DO NOTHING
                    RETURNING record_id
                    """,
                    record.record_id,
                    source_id,
                    str(record.source.url),
                    str(record.source.canonical_url),
                    record.content.title,
                    json.dumps(record.content.authors),
                    str(record.content.paper_url),
                    str(record.content.github_url) if record.content.github_url else None,
                    record.content.github_stars,
                    record.content.published_date,
                    record.provenance.raw_document_id,
                    record.provenance.content_hash,
                    record.provenance.retrieved_at,
                    json.dumps(record.model_dump(mode="json", by_alias=True)),
                )
        return PersistenceResult(record_id=record.record_id, inserted=inserted_id is not None)


def _raw_metadata(document: RawDocument) -> dict[str, object]:
    return {
        "status_code": document.status_code,
        "headers": document.headers,
        "content_type": document.content_type,
    }
