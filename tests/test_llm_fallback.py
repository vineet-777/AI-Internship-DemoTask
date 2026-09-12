from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from src.extraction.orchestrator import LLMOrchestrator
from src.extraction.providers.base import ExtractionResult, ProviderError


class ProductFacts(BaseModel):
    startup_name: str = Field(alias="startupName")
    pricing_model: str = Field(alias="pricingModel")


class FailingProvider:
    model = "test-model"

    def __init__(self, name: str, error: ProviderError) -> None:
        self.name = name
        self.error = error
        self.calls = 0

    async def extract(self, prompt: str, schema: type[BaseModel]) -> ExtractionResult:
        self.calls += 1
        raise self.error


class SuccessfulProvider:
    name = "groq"
    model = "test-model"

    async def extract(self, prompt: str, schema: type[BaseModel]) -> ExtractionResult:
        return ExtractionResult(
            provider=self.name,
            model=self.model,
            data={"startupName": "Acme AI", "pricingModel": "FREEMIUM"},
            raw_text='{"startupName":"Acme AI","pricingModel":"FREEMIUM"}',
        )


async def test_gemini_fallback_to_groq_on_429() -> None:
    gemini = FailingProvider("gemini", ProviderError("rate limited", status_code=429, retryable=True))
    groq = SuccessfulProvider()
    result = await LLMOrchestrator(
        [gemini, groq], max_attempts_per_provider=1
    ).extract("Acme AI offers a freemium product.", ProductFacts)

    assert result.provider == "groq"
    assert gemini.calls == 1


async def test_all_providers_fail_raises() -> None:
    providers = [
        FailingProvider("gemini", ProviderError("rate limited", status_code=429, retryable=True)),
        FailingProvider("groq", ProviderError("server error", status_code=500, retryable=True)),
        FailingProvider("deepseek", ProviderError("timeout", retryable=True)),
    ]

    with pytest.raises(RuntimeError, match="All providers exhausted"):
        await LLMOrchestrator(providers, max_attempts_per_provider=1).extract(
            "Acme AI offers a freemium product.", ProductFacts
        )