"""Generate the three-page architecture.pdf required by the implementation plan."""

from __future__ import annotations

import argparse
from pathlib import Path

PAGE_WIDTH = 612
PAGE_HEIGHT = 792

PAGES = (
    (
        "AI Intelligence Ingestion Pipeline",
        [
            "Sources -> Discovery -> Queue -> Async Workers",
            "Fetch / Browser -> Raw Store -> Normalize -> Freshness Gate",
            "LLM Router -> Validation -> Entity Resolution -> PostgreSQL",
            "PostgreSQL -> Vector Store / Graph Store -> Google Sheets",
            "Cross-cutting: provenance, idempotency, caching, observability, quarantine",
        ],
    ),
    (
        "Reliability Flows",
        [
            "413 CONTEXT TOO LARGE",
            "token estimate -> semantic heading/paragraph chunks -> extraction",
            "-> deterministic merge -> final schema validation",
            "",
            "429 RATE LIMIT",
            "Retry-After -> bounded exponential backoff + jitter -> retry budget",
            "-> fallback provider -> circuit breaker -> quarantine on exhaustion",
        ],
    ),
    (
        "Scale and Freshness",
        [
            "500k+ records -> partitioned queue -> stateless workers -> shared durable storage",
            "Scale capacity by adding workers; apply source/provider limits and backpressure",
            "",
            "source URL -> canonical URL -> idempotency key -> database uniqueness",
            "publication date -> priority parser -> UTC normalization -> 24-hour gate",
            "fresh records -> watermark -> validated export; stale/future/unknown -> reject or quarantine",
        ],
    ),
)


def generate_pdf(destination: Path | str = "architecture.pdf") -> Path:
    destination = Path(destination)
    pages: list[bytes] = []
    objects: list[bytes] = []
    font_id = _add_object(objects, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []
    for title, lines in PAGES:
        stream_lines = ["BT", "/F1 18 Tf", "50 740 Td", f"({_escape(title)}) Tj", "/F1 11 Tf"]
        for line in lines:
            stream_lines.extend(["0 -28 Td", f"({_escape(line)}) Tj"])
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("ascii")
        stream_id = _add_object(objects, f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
        page_id = _add_object(objects, f"<< /Type /Page /Parent PAGES /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {stream_id} 0 R >>".encode())
        page_ids.append(page_id)
    pages_id = _add_object(objects, b"")
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{ ' '.join(f'{page_id} 0 R' for page_id in page_ids) }] /Count {len(page_ids)} >>".encode()
    for page_id in page_ids:
        objects[page_id - 1] = objects[page_id - 1].replace(b"PAGES", f"{pages_id} 0 R".encode())
    catalog_id = _add_object(objects, f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())
    pdf = _serialize(objects, catalog_id)
    destination.write_bytes(pdf)
    return destination


def _add_object(objects: list[bytes], value: bytes) -> int:
    objects.append(value)
    return len(objects)


def _serialize(objects: list[bytes], root_id: int) -> bytes:
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, value in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode())
        output.extend(value)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    output.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]))
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root {root_id} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("architecture.pdf"))
    args = parser.parse_args()
    generate_pdf(args.output)
