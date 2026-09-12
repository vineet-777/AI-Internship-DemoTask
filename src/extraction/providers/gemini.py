"""Gemini structured-output provider using the Generative Language REST API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel

from src.extraction.providers.base import ExtractionResult, LLMProvider, ProviderError


@dataclass(frozen=True, slots=True)
class GeminiSettings:
    api_key: str
    model: str = "gemini-2.5-flash"
    endpoint: str = "https://generativelanguage.googleapis.com/v1beta/models"
    timeout_seconds: float = 30.0


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self,
        settings: GeminiSettings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not settings.api_key:
            raise ValueError("GEMINI_API_KEY is required for GeminiProvider")
        self.model = settings.model
        self._settings = settings
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> "GeminiProvider":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._settings.timeout_seconds)
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def extract(self, prompt: str, schema: type[BaseModel]) -> ExtractionResult:
        client = self._client
        owns_request_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=self._settings.timeout_seconds)
        endpoint = f"{self._settings.endpoint.rstrip('/')}/{self.model}:generateContent"
        try:
            response = await client.post(
                endpoint,
                params={"key": self._settings.api_key},
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0,
                        "responseMimeType": "application/json",
                        "responseSchema": schema.model_json_schema(),
                    },
                },
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderError(f"Gemini request failed: {exc}", retryable=True) from exc
        finally:
            if owns_request_client:
                await client.aclose()

        if response.status_code >= 400:
            raise ProviderError(
                f"Gemini returned HTTP {response.status_code}: {response.text[:500]}",
                status_code=response.status_code,
                retryable=response.status_code == 429 or response.status_code >= 500,
            )
        try:
            payload = response.json()
            raw_text = payload["candidates"][0]["content"]["parts"][0]["text"]
            usage = payload.get("usageMetadata", {})
            data = _parse_json_object(raw_text)
        except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError("Gemini returned an invalid structured response") from exc
        if not isinstance(raw_text, str) or not isinstance(data, dict):
            raise ProviderError("Gemini response content must be a JSON object")
        return ExtractionResult(
            provider=self.name,
            model=self.model,
            data=data,
            raw_text=raw_text,
            input_tokens=_token_value(usage, "promptTokenCount"),
            output_tokens=_token_value(usage, "candidatesTokenCount"),
        )


def _parse_json_object(value: str) -> dict[str, Any]:
    text = value.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("structured response must be an object")
    return parsed


def _token_value(usage: object, key: str) -> int | None:
    if isinstance(usage, dict) and isinstance(usage.get(key), int):
        return usage[key]
    return None
