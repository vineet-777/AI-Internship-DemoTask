"""URL and normalized-content duplicate prevention."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.parsing.identity import canonicalize_url, content_hash, deterministic_record_id


@dataclass(slots=True)
class DedupeIndex:
    source_ids_by_url: set[str] = field(default_factory=set)
    content_hashes: set[str] = field(default_factory=set)
    path: Path | None = None

    def __post_init__(self) -> None:
        if self.path is None or not self.path.exists():
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.source_ids_by_url.update(payload.get("source_ids_by_url", []))
        self.content_hashes.update(payload.get("content_hashes", []))

    def check_and_add(self, source_id: str, url: str, content: str) -> bool:
        canonical_url = canonicalize_url(url)
        url_key = deterministic_record_id(source_id, canonical_url)
        hash_key = content_hash(_normalize_content(content).encode("utf-8"))
        if url_key in self.source_ids_by_url or hash_key in self.content_hashes:
            return False
        self.source_ids_by_url.add(url_key)
        self.content_hashes.add(hash_key)
        self._persist()
        return True

    def _persist(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "source_ids_by_url": sorted(self.source_ids_by_url),
                    "content_hashes": sorted(self.content_hashes),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def _normalize_content(content: str) -> str:
    return " ".join(content.split()).casefold()
