from __future__ import annotations

from datetime import UTC, datetime

import httpx

from src.crawlers.startup.ycombinator import YCombinatorAdapter, YCombinatorSourceSettings
from src.fetch.http_client import AsyncHttpClient
from src.fetch.retry import RetryPolicy
from src.schemas.startup import StartupRecord


async def test_ycombinator_adapter_discovers_pages_and_parses_json_ld() -> None:
    html = b'''<script type="application/ld+json">{"@type":"Organization","name":"Acme AI","url":"https://www.ycombinator.com/companies/acme-ai","description":"AI tools","address":{"addressLocality":"San Francisco"},"foundingDate":"2021-04-01","numberOfEmployees":{"value":12}}</script>'''

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=html, request=request)

    async with AsyncHttpClient(
        timeout_seconds=1, connect_timeout_seconds=1, max_concurrency=2,
        retry_policy=RetryPolicy(1, 0, 0, 0), user_agent="test-agent",
        transport=httpx.MockTransport(handler),
    ) as client:
        adapter = YCombinatorAdapter(
            YCombinatorSourceSettings("ycombinator", "YC", "https://www.ycombinator.com/companies", 100, 201, True),
            client,
        )
        pages = await adapter.discover()
        assert pages[-1:] == ["https://www.ycombinator.com/companies?page=3"]
        candidate = adapter.parse(await adapter.fetch("https://www.ycombinator.com/companies?page=1"))[0]

    assert candidate.entity_name == "Acme AI"
    assert candidate.data["employeeCount"] == 12
    assert candidate.data["foundedYear"] == 2021


def test_startup_record_schema_uses_assignment_shape() -> None:
    record = StartupRecord(
        recordId="record-1", schemaVersion="1.0", recordType="STARTUP",
        source={"name": "YC", "url": "https://www.ycombinator.com/companies/acme-ai", "canonicalUrl": "https://www.ycombinator.com/companies/acme-ai"},
        collectedAt=datetime.now(UTC),
        provenance={"retrievedAt": datetime.now(UTC), "contentHash": "a" * 64, "rawDocumentId": "raw-1", "extractionMethod": "deterministic", "extractionMetadata": {}, "validationStatus": "VALID"},
        content={"entityName": "Acme AI", "data": {"employeeCount": 12}},
    )
    assert record.content.data.employee_count == 12
