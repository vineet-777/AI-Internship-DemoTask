from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx

from src.crawlers.product.producthunt import ProductHuntAdapter, ProductHuntSourceSettings
from src.crawlers.startup.ycombinator import YCombinatorAdapter, YCombinatorSourceSettings
from src.fetch.http_client import AsyncHttpClient
from src.fetch.retry import RetryPolicy
from src.jobs.product_ingestion import ProductIngestionJob
from src.jobs.startup_ingestion import StartupIngestionJob
from src.schemas.product import ProductRecord
from src.schemas.startup import StartupRecord
from src.storage.base import PersistenceResult
from src.storage.object_store import LocalRawStore, RawDocument


class RecordingRepository:
    def __init__(self) -> None:
        self.records: dict[str, object] = {}
        self.raw_documents: dict[str, RawDocument] = {}

    async def upsert(
        self,
        record: object,
        raw_documents: list[RawDocument],
        *,
        source_id: str,
    ) -> PersistenceResult:
        for raw_document in raw_documents:
            self.raw_documents[raw_document.raw_document_id] = raw_document
        record_key = getattr(record, "record_id", None)
        if record_key in self.records:
            return PersistenceResult(record_id=str(record_key), inserted=False)
        self.records[str(record_key)] = record
        return PersistenceResult(record_id=str(record_key), inserted=True)


async def test_startup_ingestion_job_persists_canonical_record(tmp_path: Path) -> None:
    html = b'''<script type="application/ld+json">{"@type":"Organization","name":"Acme AI","url":"https://www.ycombinator.com/companies/acme-ai","description":"AI tools","address":{"addressLocality":"San Francisco"},"foundingDate":"2021-04-01","numberOfEmployees":{"value":12}}</script>'''

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=html, request=request)

    repository = RecordingRepository()
    async with AsyncHttpClient(
        timeout_seconds=1,
        connect_timeout_seconds=1,
        max_concurrency=2,
        retry_policy=RetryPolicy(1, 0, 0, 0),
        user_agent="test-agent",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        job = StartupIngestionJob(
            adapter=YCombinatorAdapter(
                YCombinatorSourceSettings(
                    "ycombinator",
                    "YC",
                    "https://www.ycombinator.com/companies",
                    100,
                    10,
                    True,
                ),
                http_client,
            ),
            raw_store=LocalRawStore(tmp_path / "raw"),
            repository=repository,
        )
        first = await job.run()
        second = await job.run()

    assert first.inserted_records == 1
    assert first.discovered_urls == 1
    assert second.duplicates_prevented == 1
    record = next(iter(repository.records.values()))
    assert isinstance(record, StartupRecord)
    assert record.content.entity_name == "Acme AI"
    assert record.content.data.employee_count == 12


async def test_product_ingestion_job_persists_canonical_record(tmp_path: Path) -> None:
    html = b'''<script type="application/ld+json">{"@type":"Product","name":"Acme Copilot","url":"https://www.producthunt.com/products/acme-copilot","brand":{"name":"Acme AI"},"description":"An AI assistant","offers":{"price":0}}</script>'''

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=html, request=request)

    repository = RecordingRepository()
    async with AsyncHttpClient(
        timeout_seconds=1,
        connect_timeout_seconds=1,
        max_concurrency=2,
        retry_policy=RetryPolicy(1, 0, 0, 0),
        user_agent="test-agent",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        job = ProductIngestionJob(
            adapter=ProductHuntAdapter(
                ProductHuntSourceSettings(
                    "product_hunt",
                    "Product Hunt",
                    "https://www.producthunt.com/search?query=ai",
                    100,
                    10,
                    True,
                ),
                http_client,
            ),
            raw_store=LocalRawStore(tmp_path / "raw"),
            repository=repository,
        )
        summary = await job.run()

    assert summary.inserted_records == 1
    record = next(iter(repository.records.values()))
    assert isinstance(record, ProductRecord)
    assert record.content.product_name == "Acme Copilot"
    assert record.content.startup_name == "Acme AI"
    assert record.content.pricing_model == "FREE"
    assert record.collected_at.tzinfo is not None