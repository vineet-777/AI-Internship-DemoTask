"""Provider-neutral contracts for structured LLM extraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


class ProviderError(RuntimeError):
    """A provider could not return a usable structured response."""


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    provider: str
    model: str
    data: dict[str, Any]
    raw_text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMProvider(ABC):
    """Provider interface owned by orchestration, not source adapters."""

    name: str
    model: str

    @abstractmethod
    async def extract(self, prompt: str, schema: type[BaseModel]) -> ExtractionResult:
        """Return JSON-shaped data for the requested schema."""
