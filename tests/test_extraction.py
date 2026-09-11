from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel, Field

from src.extraction.chunker import chunk_document
from src.extraction.orchestrator import LLMOrchestrator
from src.extraction.providers.groq import GroqProvider, GroqSettings
from src.extraction.validators import ExtractionValidationError, validate_extraction


class ProductFacts(BaseModel):
    startup_name: str = Field(alias="startupName")
    pricing_model: str = Field(alias="pricingModel")


class FakeProvider:
    name = "fake"
    model = "test-model"

    async def extract(self, prompt: str, schema: type[BaseModel]):
        from src.extraction.providers.base import ExtractionResult

        return ExtractionResult(
            provider=self.name,
            model=self.model,
            data={"startupName": "Acme AI", "pricingModel": "FREEMIUM"},
            raw_text='{"startupName":"Acme AI","pricingModel":"FREEMIUM"}',
        )


def test_chunker_preserves_headings_and_paragraph_boundaries() -> None:
    chunks = chunk_document("# Intro\n\nFirst paragraph.\n\nSecond paragraph.", 6, source_record_id="doc")
    assert chunks[0].section == "Intro"
    assert [chunk.sequence for chunk in chunks] == [0, 1]
    assert all(chunk.token_estimate <= 6 for chunk in chunks)


async def test_orchestrator_returns_validated_structured_output() -> None:
    result = await LLMOrchestrator(FakeProvider(), chunk_target_tokens=100).extract(
        "Acme AI offers a freemium product.", ProductFacts, source_record_id="product-1"
    )
    assert result.value.startup_name == "Acme AI"
    assert result.provider == "fake"


def test_validator_rejects_invalid_schema_output() -> None:
    with pytest.raises(ExtractionValidationError):
        validate_extraction({"startupName": "Acme AI"}, ProductFacts)


async def test_groq_provider_parses_openai_compatible_structured_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "llama-3.3-70b-versatile"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"startupName":"Acme AI","pricingModel":"FREE"}'}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 8},
            },
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GroqProvider(GroqSettings("test-key"), client=client)
        result = await provider.extract("extract", ProductFacts)

    assert result.data["pricingModel"] == "FREE"
    assert result.input_tokens == 20
