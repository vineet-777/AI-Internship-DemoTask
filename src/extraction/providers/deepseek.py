"""DeepSeek provider slot reserved for the later fallback milestone."""

from __future__ import annotations

from pydantic import BaseModel

from src.extraction.providers.base import ExtractionResult, LLMProvider, ProviderError


class DeepSeekProvider(LLMProvider):
    name = "deepseek"
    model = "deepseek-chat"

    async def extract(self, prompt: str, schema: type[BaseModel]) -> ExtractionResult:
        raise ProviderError("DeepSeek fallback is not enabled in the first provider milestone")
