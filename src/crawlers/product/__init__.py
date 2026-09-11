"""Product source adapters."""

from src.crawlers.product.base import ProductCandidate, ProductSourceAdapter
from src.crawlers.product.producthunt import ProductHuntAdapter, ProductHuntSourceSettings

__all__ = [
    "ProductCandidate",
    "ProductSourceAdapter",
    "ProductHuntAdapter",
    "ProductHuntSourceSettings",
]
