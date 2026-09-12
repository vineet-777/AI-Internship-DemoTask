"""Provider-neutral extraction orchestration with fallback and circuits."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel

from src.extraction.circuit_breaker import CircuitBreaker
from src.extraction.chunker import Chunk, chunk_document, estimate_tokens
from src.extraction.merge import merge_extractions
from src.extraction.prompts import build_extraction_prompt
from src.extraction.providers.base import ExtractionResult, LLMProvider, ProviderError
from src.extraction.validators import validate_extraction


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    value: BaseModel
    provider: str
    model: str
    chunks: tuple[Chunk, ...]
    estimated_input_tokens: int


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass(slots=True)
class ProviderHealth:
    successes: int = 0
    failures: int = 0
    state: CircuitState = CircuitState.CLOSED

    @property
    def attempts(self) -> int:
        return self.successes + self.failures

    @property
    def failure_rate(self) -> float:
        return self.failures / self.attempts if self.attempts else 0.0


class LLMOrchestrator:
    """Extract complete documents with an ordered, health-aware fallback chain."""

    def __init__(
        self,
        providers: list[LLMProvider] | LLMProvider,
        *,
        chunk_target_tokens: int = 5_000,
        max_attempts_per_provider: int = 2,
        circuit_failure_threshold: int = 5,
        circuit_cooldown_seconds: float = 60.0,
        retry_base_delay_seconds: float = 0.25,
        retry_max_delay_seconds: float = 8.0,
        retry_jitter_seconds: float = 0.1,
    ) -> None:
        provider_list = providers if isinstance(providers, list) else [providers]
        if not provider_list:
            raise ValueError("At least one LLM provider is required")
        if len({provider.name for provider in provider_list}) != len(provider_list):
            raise ValueError("LLM provider names must be unique")
        if max_attempts_per_provider < 1:
            raise ValueError("max_attempts_per_provider must be positive")
        if retry_base_delay_seconds < 0 or retry_max_delay_seconds < 0 or retry_jitter_seconds < 0:
            raise ValueError("retry delays must not be negative")
        self._providers = {provider.name: provider for provider in provider_list}
        self._provider_order = tuple(provider.name for provider in provider_list)
        self._circuit_breakers = {
            name: CircuitBreaker(circuit_failure_threshold, circuit_cooldown_seconds)
            for name in self._providers
        }
        self._health = {name: ProviderHealth() for name in self._providers}
        self._chunk_target_tokens = chunk_target_tokens
        self._max_attempts = max_attempts_per_provider
        self._retry_base_delay = retry_base_delay_seconds
        self._retry_max_delay = retry_max_delay_seconds
        self._retry_jitter = retry_jitter_seconds
        self._health_lock = asyncio.Lock()

    async def extract(
        self,
        text: str,
        schema: type[BaseModel],
        *,
        source_record_id: str = "unknown",
        source_context: str | None = None,
    ) -> OrchestrationResult:
        chunks = chunk_document(text, self._chunk_target_tokens, source_record_id=source_record_id)
        if not chunks:
            raise ValueError("Cannot extract from an empty document")
        last_error: Exception | None = None
        for provider_name in await self._fallback_order():
            if not await self._can_execute(provider_name):
                continue
            provider = self._providers[provider_name]
            try:
                results = await self._extract_all_chunks(
                    chunks, schema, provider_name, provider, source_context=source_context
                )
                merged = merge_extractions([result.data for result in results])
                value = validate_extraction(merged, schema)
            except Exception as error:
                last_error = error
                if not _should_fallback(error):
                    raise
                continue
            await self._record_success(provider_name)
            return OrchestrationResult(
                value=value,
                provider=provider_name,
                model=results[0].model,
                chunks=tuple(chunks),
                estimated_input_tokens=sum(estimate_tokens(chunk.text) for chunk in chunks),
            )
        raise RuntimeError("All providers exhausted") from last_error

    async def _extract_all_chunks(
        self,
        chunks: list[Chunk],
        schema: type[BaseModel],
        provider_name: str,
        provider: LLMProvider,
        *,
        source_context: str | None,
    ) -> list[ExtractionResult]:
        results: list[ExtractionResult] = []
        for chunk in chunks:
            results.extend(
                await self._extract_chunk(
                    chunk,
                    schema,
                    provider_name,
                    provider,
                    source_context=source_context,
                )
            )
        return results

    async def _extract_chunk(
        self,
        chunk: Chunk,
        schema: type[BaseModel],
        provider_name: str,
        provider: LLMProvider,
        *,
        source_context: str | None,
    ) -> list[ExtractionResult]:
        prompt = build_extraction_prompt(chunk.text, schema, source_context=source_context)
        for attempt in range(self._max_attempts):
            try:
                return [await provider.extract(prompt, schema)]
            except ProviderError as error:
                if error.status_code == 413:
                    smaller_target = max(1, chunk.token_estimate // 2)
                    if smaller_target >= chunk.token_estimate:
                        raise
                    smaller_chunks = chunk_document(
                        chunk.text,
                        smaller_target,
                        source_record_id=chunk.source_record_id,
                    )
                    if len(smaller_chunks) <= 1 and smaller_target == 1:
                        raise
                    recovered: list[ExtractionResult] = []
                    for smaller_chunk in smaller_chunks:
                        recovered.extend(
                            await self._extract_chunk(
                                smaller_chunk,
                                schema,
                                provider_name,
                                provider,
                                source_context=source_context,
                            )
                        )
                    return recovered
                await self._record_failure(provider_name)
                if attempt + 1 >= self._max_attempts:
                    raise
                await self._backoff(attempt)
            except Exception:
                await self._record_failure(provider_name)
                if attempt + 1 >= self._max_attempts:
                    raise
                await self._backoff(attempt)
        raise RuntimeError("Provider extraction attempts exhausted")

    async def _backoff(self, attempt: int) -> None:
        delay = min(self._retry_max_delay, self._retry_base_delay * (2**attempt))
        if self._retry_jitter:
            delay += random.uniform(0, self._retry_jitter)
        if delay:
            await asyncio.sleep(delay)

    async def _fallback_order(self) -> list[str]:
        async with self._health_lock:
            return [
                name
                for _, _, name in sorted(
                    (
                        self._health[name].failure_rate,
                        index,
                        name,
                    )
                    for index, name in enumerate(self._provider_order)
                )
            ]

    async def _can_execute(self, provider_name: str) -> bool:
        async with self._health_lock:
            breaker = self._circuit_breakers[provider_name]
            allowed = breaker.can_execute()
            self._health[provider_name].state = CircuitState(
                ("CLOSED", "OPEN", "HALF_OPEN")[breaker.state]
            )
            return allowed

    async def _record_failure(self, provider_name: str) -> None:
        async with self._health_lock:
            self._health[provider_name].failures += 1
            breaker = self._circuit_breakers[provider_name]
            breaker.record_failure()
            self._health[provider_name].state = CircuitState(
                ("CLOSED", "OPEN", "HALF_OPEN")[breaker.state]
            )

    async def _record_success(self, provider_name: str) -> None:
        async with self._health_lock:
            self._health[provider_name].successes += 1
            self._circuit_breakers[provider_name].record_success()
            self._health[provider_name].state = CircuitState.CLOSED


def _should_fallback(error: Exception) -> bool:
    if isinstance(error, ProviderError):
        return error.retryable or error.status_code in {413, 429} or (
            error.status_code is not None and error.status_code >= 500
        )
    return isinstance(error, (asyncio.TimeoutError, TimeoutError))
