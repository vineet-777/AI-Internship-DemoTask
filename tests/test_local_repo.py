"""Tests for LocalIntelligenceRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.schemas.common import Provenance, SourceReference
from src.schemas.startup import StartupContent, StartupData, StartupRecord
from src.storage.local import LocalIntelligenceRepository
from src.storage.object_store import RawDocument


@pytest.mark.asyncio
async def test_local_repository_upsert_and_read() -> None:
    with TemporaryDirectory() as tmpdir:
        repo = LocalIntelligenceRepository(tmpdir)
        raw_doc = RawDocument(
            raw_document_id="raw-1",
            source_id="ycombinator",
            original_url="https://ycombinator.com/companies/openai",
            canonical_url="https://ycombinator.com/companies/openai",
            content_hash="a" * 64,
            retrieved_at=datetime.now(UTC),
            storage_key="test.html",
            status_code=200,
            headers={},
            content_type="text/html",
        )
        record = StartupRecord(
            record_id="b" * 64,
            collected_at=datetime.now(UTC),
            schema_version="1.0",
            record_type="STARTUP",
            source=SourceReference(
                name="ycombinator",
                url="https://ycombinator.com/companies/openai",
                canonical_url="https://ycombinator.com/companies/openai",
            ),
            provenance=Provenance(
                retrieved_at=datetime.now(UTC),
                content_hash="a" * 64,
                raw_document_id="raw-1",
                extraction_method="deterministic",
                extraction_metadata={"llm_used": False},
                validation_status="VALID",
            ),
            content=StartupContent(
                entity_name="OpenAI",
                data=StartupData(
                    employee_count=1000,
                    description="AI research and deployment company",
                ),
            ),
        )

        res1 = await repo.upsert(record, [raw_doc], source_id="ycombinator")
        assert res1.inserted is True

        # Idempotent re-insert
        res2 = await repo.upsert(record, [raw_doc], source_id="ycombinator")
        assert res2.inserted is False

        tabs = repo.read_tabs()
        assert len(tabs["Startups"]) == 1
        assert tabs["Startups"][0]["content"]["entityName"] == "OpenAI"
