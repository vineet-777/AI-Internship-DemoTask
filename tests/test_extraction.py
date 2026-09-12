from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel, Field

from src.extraction.chunker import chunk_document
from src.extraction.orchestrator import CircuitState, LLMOrchestrator
from src.extraction.providers.deepseek import DeepSeekProvider, DeepSeekSettings
from src.extraction.providers.gemini import GeminiProvider, GeminiSettings
from src.extraction.providers.base import ExtractionResult, ProviderError
from src.extraction.providers.circuit_breaker import CircuitBreaker
from src.extraction.providers.groq import GroqProvider, GroqSettings
from src.extraction.validators import ExtractionValidationError, validate_extraction


class ProductFacts(BaseModel):
    startup_name: str = Field(alias="startupName")
    pricing_model: str = Field(alias="pricingModel")


class FakeProvider:
    name = "fake"
    model = "test-model"

    async def extract(self, prompt: str, schema: type[BaseModel]):
        return ExtractionResult(
            provider=self.name,
            model=self.model,
            data={"startupName": "Acme AI", "pricingModel": "FREEMIUM"},
            raw_text='{"startupName":"Acme AI","pricingModel":"FREEMIUM"}',
        )


class FlakyProvider:
    name = "flaky"
    model = "flaky-model"

    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, prompt: str, schema: type[BaseModel]) -> ExtractionResult:
        self.calls += 1
        raise ProviderError("rate limited", status_code=429, retryable=True)


class RecoveryProvider:
    name = "recovery"
    model = "recovery-model"

    async def extract(self, prompt: str, schema: type[BaseModel]) -> ExtractionResult:
        return ExtractionResult(
            provider=self.name,
            model=self.model,
            data={"startupName": "Acme AI", "pricingModel": "FREEMIUM"},
            raw_text='{"startupName":"Acme AI","pricingModel":"FREEMIUM"}',
        )


class PayloadLimitProvider:
    name = "payload-limit"
    model = "payload-model"

    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, prompt: str, schema: type[BaseModel]) -> ExtractionResult:
        self.calls += 1
        if self.calls == 1:
            raise ProviderError("payload too large", status_code=413)
        return ExtractionResult(
            provider=self.name,
            model=self.model,
            data={"startupName": "Acme AI", "pricingModel": "FREEMIUM"},
            raw_text='{"startupName":"Acme AI","pricingModel":"FREEMIUM"}',
        )


def test_circuit_breaker_opens_after_threshold_and_allows_one_probe() -> None:
    now = 0.0
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=10, clock=lambda: now)

    assert breaker.can_execute()
    breaker.record_failure()
    assert breaker.state == CircuitBreaker.CLOSED
    breaker.record_failure()
    assert breaker.state == CircuitBreaker.OPEN
    assert not breaker.can_execute()

    now = 10.0
    assert breaker.can_execute()
    assert breaker.state == CircuitBreaker.HALF_OPEN
    assert not breaker.can_execute()
    breaker.record_success()
    assert breaker.state == CircuitBreaker.CLOSED
    assert breaker.failure_count == 0


def test_circuit_breaker_reopens_when_half_open_probe_fails() -> None:
    now = 0.0
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=5, clock=lambda: now)
    breaker.record_failure()
    now = 5.0
    assert breaker.can_execute()
    breaker.record_failure()
    assert breaker.state == CircuitBreaker.OPEN


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


async def test_orchestrator_retries_then_falls_back_and_opens_failed_circuit() -> None:
    flaky = FlakyProvider()
    recovery = RecoveryProvider()
    orchestrator = LLMOrchestrator(
        [flaky, recovery],
        chunk_target_tokens=100,
        max_attempts_per_provider=2,
        circuit_failure_threshold=2,
    )

    result = await orchestrator.extract("Acme AI offers a freemium product.", ProductFacts)

    assert result.provider == "recovery"
    assert flaky.calls == 2
    assert orchestrator._health["flaky"].state == CircuitState.OPEN
    assert orchestrator._health["flaky"].failures == 2
    assert orchestrator._health["recovery"].successes == 1


async def test_orchestrator_recovers_from_413_by_rechunking() -> None:
    provider = PayloadLimitProvider()
    result = await LLMOrchestrator(
        provider,
        chunk_target_tokens=100,
        max_attempts_per_provider=1,
        retry_base_delay_seconds=0,
        retry_jitter_seconds=0,
    ).extract("Acme AI offers a freemium product.", ProductFacts)

    assert result.value.startup_name == "Acme AI"
    assert provider.calls > 1


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


async def test_gemini_provider_parses_generate_content_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert str(request.url) == "https://gemini.test/v1beta/models/gemini-2.5-flash:generateContent?key=test-key"
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["generationConfig"]["responseSchema"]["type"] == "object"
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": '{"startupName":"Acme AI","pricingModel":"PAID"}'}]}}],
                "usageMetadata": {"promptTokenCount": 24, "candidatesTokenCount": 9},
            },
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GeminiProvider(
            GeminiSettings("test-key", endpoint="https://gemini.test/v1beta/models"),
            client=client,
        )
        result = await provider.extract("extract", ProductFacts)

    assert result.provider == "gemini"
    assert result.model == "gemini-2.5-flash"
    assert result.data["pricingModel"] == "PAID"
    assert result.input_tokens == 24


async def test_deepseek_provider_parses_openai_compatible_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert str(request.url) == "https://deepseek.test/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert body["model"] == "deepseek-chat"
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"startupName":"Acme AI","pricingModel":"ENTERPRISE"}'}}],
                "usage": {"prompt_tokens": 32, "completion_tokens": 10},
            },
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DeepSeekProvider(
            DeepSeekSettings("test-key", endpoint="https://deepseek.test/v1/chat/completions"),
            client=client,
        )
        result = await provider.extract("extract", ProductFacts)

    assert result.provider == "deepseek"
    assert result.model == "deepseek-chat"
    assert result.data["pricingModel"] == "ENTERPRISE"
    assert result.output_tokens == 10
