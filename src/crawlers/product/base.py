"""Shared product adapter contract and source-neutral candidate model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.crawlers.base import SourceAdapter
from src.fetch.http_client import RawResponse
from src.schemas.product import PricingModel


@dataclass(frozen=True, slots=True)
class ProductCandidate:
    """Facts extracted directly from one product source entry."""

    original_url: str
    canonical_url: str
    product_name: str
    startup_name: str
    pricing_model: PricingModel
    data: dict[str, Any]


class ProductSourceAdapter(SourceAdapter[ProductCandidate]):
    """Base interface for product sources with paginated discovery."""

    async def fetch(self, url: str) -> RawResponse:
        raise NotImplementedError
