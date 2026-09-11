"""Source adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from src.fetch.http_client import RawResponse

T = TypeVar("T")


class SourceAdapter(ABC, Generic[T]):
    source_id: str
    source_name: str

    @abstractmethod
    async def discover(self) -> list[str]:
        """Return source URLs ready for acquisition."""

    @abstractmethod
    async def fetch(self, url: str) -> RawResponse:
        """Fetch a URL through the shared acquisition layer."""

    @abstractmethod
    def parse(self, response: RawResponse) -> list[T]:
        """Parse source evidence without inferring unsupported facts."""
