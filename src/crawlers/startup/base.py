"""Shared startup adapter contract and source-neutral candidate model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.crawlers.base import SourceAdapter
from src.fetch.http_client import RawResponse


@dataclass(frozen=True, slots=True)
class StartupCandidate:
    """Facts extracted directly from one startup source entry."""

    original_url: str
    canonical_url: str
    entity_name: str
    data: dict[str, Any]


class StartupSourceAdapter(SourceAdapter[StartupCandidate]):
    """Base interface for startup sources with paginated discovery."""

    async def fetch(self, url: str) -> RawResponse:
        raise NotImplementedError
