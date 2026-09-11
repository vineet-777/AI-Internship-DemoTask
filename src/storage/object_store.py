"""Content-addressed local raw-evidence store for the demo environment."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from src.fetch.http_client import RawResponse
from src.parsing.identity import (
    canonicalize_url,
    content_hash,
    deterministic_raw_document_id,
)


@dataclass(frozen=True, slots=True)
class RawDocument:
    raw_document_id: str
    source_id: str
    original_url: str
    canonical_url: str
    content_hash: str
    retrieved_at: datetime
    status_code: int
    headers: dict[str, str]
    storage_key: str
    content_type: str | None


class LocalRawStore:
    """Persist the unmodified response before parsing or semantic extraction."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    async def put(self, source_id: str, response: RawResponse) -> RawDocument:
        hash_value = content_hash(response.body)
        canonical_url = canonicalize_url(response.response_url)
        raw_document_id = deterministic_raw_document_id(source_id, canonical_url, hash_value)
        retrieved = response.retrieved_at
        relative_directory = Path(source_id) / retrieved.strftime("%Y") / retrieved.strftime("%m") / retrieved.strftime("%d")
        extension = _extension_for(response.headers.get("content-type"))
        relative_blob = relative_directory / f"{hash_value}{extension}"
        relative_metadata = relative_directory / f"{hash_value}.metadata.json"
        document = RawDocument(
            raw_document_id=raw_document_id,
            source_id=source_id,
            original_url=response.request_url,
            canonical_url=canonical_url,
            content_hash=hash_value,
            retrieved_at=retrieved,
            status_code=response.status_code,
            headers=response.headers,
            storage_key=relative_blob.as_posix(),
            content_type=response.headers.get("content-type"),
        )
        await asyncio.to_thread(self._persist_sync, relative_blob, response.body)
        await asyncio.to_thread(
            self._persist_sync,
            relative_metadata,
            json.dumps(_document_metadata(document), sort_keys=True, indent=2).encode("utf-8"),
        )
        return document

    async def read_bytes(self, document: RawDocument) -> bytes:
        return await asyncio.to_thread((self._root / document.storage_key).read_bytes)

    def _persist_sync(self, relative_path: Path, payload: bytes) -> None:
        destination = self._root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            return
        temporary = destination.with_suffix(f"{destination.suffix}.tmp-{os.getpid()}")
        try:
            with temporary.open("xb") as handle:
                handle.write(payload)
            os.replace(temporary, destination)
        except FileExistsError:
            # Another local process won the same content-addressed write.
            return
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)


def _document_metadata(document: RawDocument) -> dict[str, object]:
    data = asdict(document)
    data["retrieved_at"] = document.retrieved_at.isoformat()
    return data


def _extension_for(content_type: str | None) -> str:
    media_type = (content_type or "").split(";", maxsplit=1)[0].lower()
    return {
        "application/atom+xml": ".xml",
        "application/xml": ".xml",
        "text/xml": ".xml",
        "application/json": ".json",
        "text/html": ".html",
    }.get(media_type, ".bin")
