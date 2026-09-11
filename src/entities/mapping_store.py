"""Append-only persistence for auditable raw-to-canonical mappings."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.entities.matcher import MatchResult


@dataclass(frozen=True, slots=True)
class MappingEntry:
    raw_name: str
    canonical_name: str | None
    source: str
    method: str
    confidence: float
    timestamp: str
    record_id: str | None = None
    status: str = "UNRESOLVED"


class MappingStore:
    """JSONL mapping log; each resolution is retained rather than overwritten."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def append(
        self,
        result: MatchResult,
        *,
        source: str,
        record_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> MappingEntry:
        entry = MappingEntry(
            raw_name=result.raw_name,
            canonical_name=result.canonical_name,
            source=source,
            method=result.method,
            confidence=result.confidence,
            timestamp=_utc(timestamp or datetime.now(UTC)).isoformat(),
            record_id=record_id,
            status=result.status.value,
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(entry), sort_keys=True) + "\n")
        return entry

    def read(self) -> list[MappingEntry]:
        if not self._path.exists():
            return []
        entries: list[MappingEntry] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(MappingEntry(**json.loads(line)))
        return entries


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
