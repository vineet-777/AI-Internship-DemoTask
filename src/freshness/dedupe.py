"""URL and normalized-content duplicate prevention."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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


class RedisDedupeIndex:
    """Distributed URL/content dedupe backed by atomic Redis key claims."""

    _CLAIM_SCRIPT = """
    if redis.call('EXISTS', KEYS[1]) == 1 or redis.call('EXISTS', KEYS[2]) == 1 then
        return 0
    end
    redis.call('SET', KEYS[1], '1')
    redis.call('SET', KEYS[2], '1')
    return 1
    """

    def __init__(
        self,
        redis_url: str,
        *,
        namespace: str = "ingestion:dedupe",
        client: Any | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._namespace = namespace
        self._redis = client
        self._owns_client = client is None

    async def connect(self) -> None:
        if self._redis is not None:
            return
        try:
            import redis.asyncio as redis
        except ImportError as exc:  # pragma: no cover - dependency/environment path
            raise RuntimeError("Install the redis package to use RedisDedupeIndex") from exc
        self._redis = redis.from_url(self._redis_url, decode_responses=True)

    async def close(self) -> None:
        if self._owns_client and self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def __aenter__(self) -> "RedisDedupeIndex":
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def check_and_add(self, source_id: str, url: str, content: str) -> bool:
        await self.connect()
        canonical_url = canonicalize_url(url)
        url_id = deterministic_record_id(source_id, canonical_url)
        hash_id = content_hash(_normalize_content(content).encode("utf-8"))
        url_key = f"{self._namespace}:url:{url_id}"
        hash_key = f"{self._namespace}:content:{hash_id}"
        claimed = await self._redis.eval(self._CLAIM_SCRIPT, 2, url_key, hash_key)
        return int(claimed) == 1
