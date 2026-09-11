"""URL and content identities used for distributed-safe idempotency."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

TRACKING_PARAMETERS = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid"})


def canonicalize_url(url: str, *, drop_parameters: Iterable[str] = TRACKING_PARAMETERS) -> str:
    """Normalize only non-semantic URL differences; preserve meaningful query keys."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Expected an absolute HTTP(S) URL, got {url!r}")

    drop = {parameter.lower() for parameter in drop_parameters}
    hostname = parsed.hostname.lower()
    port = parsed.port
    netloc = hostname if port in (None, 80, 443) else f"{hostname}:{port}"
    path = quote(unquote(parsed.path or "/"), safe="/%:@")
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(
        sorted(
            (
                (key, value)
                for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                if key.lower() not in drop and not key.lower().startswith("utm_")
            ),
            key=lambda item: (item[0], item[1]),
        ),
        doseq=True,
    )
    return urlunsplit(("https", netloc, path, query, ""))


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def deterministic_record_id(source_id: str, canonical_url: str) -> str:
    """Stable identity for a source record, suitable for a uniqueness constraint."""
    return hashlib.sha256(f"{source_id}\x1f{canonical_url}".encode("utf-8")).hexdigest()


def deterministic_raw_document_id(source_id: str, canonical_url: str, hash_value: str) -> str:
    return hashlib.sha256(f"{source_id}\x1f{canonical_url}\x1f{hash_value}".encode("utf-8")).hexdigest()


def canonicalize_arxiv_url(url: str) -> str:
    """Canonicalize an arXiv abstract URL while retaining the source URL separately."""
    canonical = canonicalize_url(url)
    match = re.fullmatch(r"/abs/([a-z-]+/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?", urlsplit(canonical).path)
    if not match:
        raise ValueError(f"Unexpected arXiv abstract URL: {url!r}")
    return f"https://arxiv.org/abs/{match.group(1)}"
