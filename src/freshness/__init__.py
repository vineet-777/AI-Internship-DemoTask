"""Freshness, watermark, and duplicate-prevention primitives."""

from src.freshness.dedupe import DedupeIndex, RedisDedupeIndex
from src.freshness.policies import FreshnessDecision, DateEvidence, evaluate_freshness, select_date
from src.freshness.watermark import WatermarkStore

__all__ = [
    "DedupeIndex",
    "RedisDedupeIndex",
    "WatermarkStore",
    "DateEvidence",
    "FreshnessDecision",
    "select_date",
    "evaluate_freshness",
]
