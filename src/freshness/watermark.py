"""Persistent per-source publication watermarks."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path


class WatermarkStore:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._values: dict[str, datetime] = {}
        if self._path.exists():
            self._load()

    def get(self, source_id: str) -> datetime | None:
        return self._values.get(source_id)

    def advance(self, source_id: str, value: datetime) -> None:
        current = self._values.get(source_id)
        if current is not None and value <= current:
            return
        self._values[source_id] = value
        self._persist()

    def _load(self) -> None:
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Watermark file must contain an object")
        for source_id, value in payload.items():
            self._values[source_id] = datetime.fromisoformat(value)

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {source_id: value.isoformat() for source_id, value in self._values.items()}
        temporary = self._path.with_suffix(f"{self._path.suffix}.tmp-{os.getpid()}")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, self._path)
