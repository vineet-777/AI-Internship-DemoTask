"""Gemini provider slot reserved for the later fallback milestone."""

from __future__ import annotations

from pydantic import BaseModel

from src.extraction.providers.base import ExtractionResult, LLMProvider, ProviderError


class GeminiProvider(LLMProvider):
    name = "gemini"
    model = "gemini-2.5-flash"

    async def extract(self, prompt: str, schema: type[BaseModel]) -> ExtractionResult:
        raise ProviderError("Gemini fallback is not enabled in the first provider milestone")
