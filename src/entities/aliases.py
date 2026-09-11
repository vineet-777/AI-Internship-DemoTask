"""Alias-table loading for seeded canonical entities."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.entities.normalizer import normalize_entity_name


@dataclass(frozen=True, slots=True)
class EntitySeed:
    entity_id: str
    canonical_name: str
    aliases: tuple[str, ...] = ()


@dataclass(slots=True)
class AliasTable:
    entities: dict[str, EntitySeed] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_seed_file(cls, path: Path | str) -> "AliasTable":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("Entity seed file must contain a list")
        table = cls()
        for item in payload:
            if not isinstance(item, dict):
                continue
            entity_id = item.get("canonicalEntityId")
            name = item.get("rawEntityName")
            aliases = item.get("aliases", [])
            if not isinstance(entity_id, str) or not isinstance(name, str):
                continue
            table.add(EntitySeed(entity_id, name, tuple(alias for alias in aliases if isinstance(alias, str))))
        return table

    def add(self, entity: EntitySeed) -> None:
        if not entity.entity_id or not entity.canonical_name.strip():
            raise ValueError("Entity seeds require an ID and canonical name")
        self.entities[entity.entity_id] = entity
        for value in (entity.canonical_name, *entity.aliases):
            key = normalize_entity_name(value)
            if not key:
                continue
            existing = self.aliases.get(key)
            if existing is not None and existing != entity.entity_id:
                raise ValueError(f"Alias {value!r} maps to multiple entities")
            self.aliases[key] = entity.entity_id

    def resolve_exact(self, value: str) -> EntitySeed | None:
        entity_id = self.aliases.get(normalize_entity_name(value))
        return self.entities.get(entity_id) if entity_id else None
