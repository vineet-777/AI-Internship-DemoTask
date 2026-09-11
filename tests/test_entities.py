from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.entities.aliases import AliasTable, EntitySeed
from src.entities.mapping_store import MappingStore
from src.entities.matcher import EntityMatcher, MatchStatus
from src.entities.normalizer import normalize_entity_name


def test_normalizer_handles_unicode_punctuation_and_legal_suffixes() -> None:
    assert normalize_entity_name("OpenAI, Inc.") == "openai"
    assert normalize_entity_name("Open AI") == "openai"
    assert normalize_entity_name("Mistrál-AI LLC") == "mistralai"


def test_alias_table_and_matcher_resolve_exact_and_alias_names() -> None:
    table = AliasTable()
    table.add(EntitySeed("startup:openai", "OpenAI", ("Open AI",)))
    matcher = EntityMatcher(table)
    result = matcher.match("OpenAI, Inc.")
    assert result.canonical_name == "OpenAI"
    assert result.status == MatchStatus.AUTO_MATCH
    assert result.confidence == 1.0


def test_matcher_has_review_and_negative_paths() -> None:
    table = AliasTable()
    table.add(EntitySeed("startup:openai", "OpenAI"))
    table.add(EntitySeed("startup:anthropic", "Anthropic"))
    matcher = EntityMatcher(table)
    review = matcher.match("Anthropic Labs")
    unresolved = matcher.match("Completely Unrelated Robotics")
    assert review.status == MatchStatus.REVIEW
    assert unresolved.status == MatchStatus.UNRESOLVED
    assert unresolved.canonical_name is None


def test_mapping_store_is_append_only_and_auditable(tmp_path: Path) -> None:
    table = AliasTable()
    table.add(EntitySeed("startup:openai", "OpenAI"))
    result = EntityMatcher(table).match("Open AI")
    store = MappingStore(tmp_path / "mappings.jsonl")
    store.append(result, source="news", record_id="record-1", timestamp=datetime(2026, 9, 11, tzinfo=UTC))
    entries = store.read()
    assert len(entries) == 1
    assert entries[0].canonical_name == "OpenAI"
    assert entries[0].source == "news"


def test_alias_table_rejects_conflicting_aliases() -> None:
    table = AliasTable()
    table.add(EntitySeed("startup:one", "One", ("Shared",)))
    with pytest.raises(ValueError):
        table.add(EntitySeed("startup:two", "Two", ("Shared",)))
