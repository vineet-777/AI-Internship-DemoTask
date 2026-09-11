from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from pydantic import ValidationError

from src.crawlers.product.producthunt import ProductHuntAdapter, ProductHuntSourceSettings
from src.fetch.http_client import AsyncHttpClient
from src.fetch.retry import RetryPolicy
from src.schemas.product import ProductRecord


async def test_product_hunt_adapter_discovers_pages_and_parses_product_json_ld() -> None:
    html = b'''<script type="application/ld+json">{"@type":"Product","name":"Acme Copilot","url":"https://www.producthunt.com/products/acme-copilot","brand":{"name":"Acme AI"},"description":"An AI assistant","offers":{"price":0}}</script>'''

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=html, request=request)

    async with AsyncHttpClient(
        timeout_seconds=1, connect_timeout_seconds=1, max_concurrency=2,
        retry_policy=RetryPolicy(1, 0, 0, 0), user_agent="test-agent",
        transport=httpx.MockTransport(handler),
    ) as client:
        adapter = ProductHuntAdapter(
            ProductHuntSourceSettings("product_hunt", "Product Hunt", "https://www.producthunt.com/search?query=ai", 100, 201, True),
            client,
        )
        pages = await adapter.discover()
        candidate = adapter.parse(await adapter.fetch(pages[0]))[0]

    assert pages[-1] == "https://www.producthunt.com/search?query=ai&page=3"
    assert candidate.product_name == "Acme Copilot"
    assert candidate.startup_name == "Acme AI"
    assert candidate.pricing_model == "FREE"


def test_product_schema_requires_startup_and_valid_pricing_model() -> None:
    record = ProductRecord(
        recordId="record-1", schemaVersion="1.0", recordType="PRODUCT",
        source={"name": "Product Hunt", "url": "https://www.producthunt.com/products/acme-copilot", "canonicalUrl": "https://www.producthunt.com/products/acme-copilot"},
        collectedAt=datetime.now(UTC),
        provenance={"retrievedAt": datetime.now(UTC), "contentHash": "b" * 64, "rawDocumentId": "raw-1", "extractionMethod": "deterministic", "extractionMetadata": {}, "validationStatus": "VALID"},
        content={"productName": "Acme Copilot", "startupName": "Acme AI", "pricingModel": "FREEMIUM"},
    )
    assert record.content.startup_name == "Acme AI"

    with pytest.raises(ValidationError):
        ProductRecord(
            recordId="record-2", schemaVersion="1.0", recordType="PRODUCT",
            source={"name": "Product Hunt", "url": "https://www.producthunt.com/products/acme-copilot", "canonicalUrl": "https://www.producthunt.com/products/acme-copilot"},
            collectedAt=datetime.now(UTC),
            provenance={"retrievedAt": datetime.now(UTC), "contentHash": "c" * 64, "rawDocumentId": "raw-2", "extractionMethod": "deterministic", "extractionMetadata": {}, "validationStatus": "VALID"},
            content={"startupName": "Acme AI", "pricingModel": "UNKNOWN"},
        )
