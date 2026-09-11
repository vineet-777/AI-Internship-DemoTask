"""Provider-neutral extraction orchestration for the first Groq milestone."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from src.extraction.chunker import Chunk, chunk_document, estimate_tokens
from src.extraction.merge import merge_extractions
from src.extraction.prompts import build_extraction_prompt
from src.extraction.providers.base import ExtractionResult, LLMProvider
from src.extraction.validators import validate_extraction


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    value: BaseModel
    provider: str
    model: str
    chunks: tuple[Chunk, ...]
    estimated_input_tokens: int


class LLMOrchestrator:
    """Chunk, prompt, call one provider, merge, and validate final output."""

    def __init__(self, provider: LLMProvider, *, chunk_target_tokens: int = 5_000) -> None:
        self._provider = provider
        self._chunk_target_tokens = chunk_target_tokens

    async def extract(
        self,
        text: str,
        schema: type[BaseModel],
        *,
        source_record_id: str = "unknown",
        source_context: str | None = None,
    ) -> OrchestrationResult:
        chunks = chunk_document(
            text,
            self._chunk_target_tokens,
            source_record_id=source_record_id,
        )
        if not chunks:
            raise ValueError("Cannot extract from an empty document")
        results: list[ExtractionResult] = []
        for chunk in chunks:
            prompt = build_extraction_prompt(chunk.text, schema, source_context=source_context)
            results.append(await self._provider.extract(prompt, schema))
        merged = merge_extractions([result.data for result in results])
        value = validate_extraction(merged, schema)
        return OrchestrationResult(
            value=value,
            provider=results[0].provider,
            model=results[0].model,
            chunks=tuple(chunks),
            estimated_input_tokens=sum(estimate_tokens(chunk.text) for chunk in chunks),
        )
