"""Exact, alias, and deterministic fuzzy entity matching."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum

from src.entities.aliases import AliasTable, EntitySeed
from src.entities.normalizer import normalize_entity_name


class MatchStatus(StrEnum):
    AUTO_MATCH = "AUTO_MATCH"
    REVIEW = "REVIEW"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class MatchResult:
    raw_name: str
    canonical_name: str | None
    canonical_entity_id: str | None
    method: str
    confidence: float
    status: MatchStatus


class EntityMatcher:
    def __init__(
        self,
        aliases: AliasTable,
        *,
        auto_threshold: float = 0.95,
        review_threshold: float = 0.80,
    ) -> None:
        if not 0 <= review_threshold <= auto_threshold <= 1:
            raise ValueError("thresholds must satisfy 0 <= review <= auto <= 1")
        self._aliases = aliases
        self._auto_threshold = auto_threshold
        self._review_threshold = review_threshold

    def match(self, raw_name: str) -> MatchResult:
        if not raw_name.strip():
            return MatchResult(raw_name, None, None, "unresolved", 0.0, MatchStatus.UNRESOLVED)
        exact = self._aliases.resolve_exact(raw_name)
        if exact is not None:
            return _result(raw_name, exact, "exact", 1.0, MatchStatus.AUTO_MATCH)

        normalized = normalize_entity_name(raw_name)
        candidates = sorted(self._aliases.entities.values(), key=lambda entity: entity.entity_id)
        scored = [
            (SequenceMatcher(None, normalized, normalize_entity_name(entity.canonical_name)).ratio(), entity)
            for entity in candidates
        ]
        if not scored:
            return MatchResult(raw_name, None, None, "unresolved", 0.0, MatchStatus.UNRESOLVED)
        confidence, entity = max(scored, key=lambda item: (item[0], item[1].entity_id))
        if confidence >= self._auto_threshold:
            return _result(raw_name, entity, "fuzzy", confidence, MatchStatus.AUTO_MATCH)
        if confidence >= self._review_threshold:
            return _result(raw_name, entity, "fuzzy", confidence, MatchStatus.REVIEW)
        return MatchResult(raw_name, None, None, "unresolved", confidence, MatchStatus.UNRESOLVED)


def _result(
    raw_name: str,
    entity: EntitySeed,
    method: str,
    confidence: float,
    status: MatchStatus,
) -> MatchResult:
    return MatchResult(raw_name, entity.canonical_name, entity.entity_id, method, confidence, status)
