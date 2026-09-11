"""Deterministic semantic chunking at heading and paragraph boundaries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    source_record_id: str
    section: str | None
    text: str
    token_estimate: int
    sequence: int


def estimate_tokens(text: str) -> int:
    """Conservative, dependency-free estimate suitable for routing decisions."""
    return max(1, ceil(len(text) / 4)) if text else 0


def chunk_document(text: str, target_tokens: int, *, source_record_id: str = "unknown") -> list[Chunk]:
    if target_tokens < 1:
        raise ValueError("target_tokens must be positive")
    blocks = _blocks(text)
    if not blocks:
        return []
    chunks: list[Chunk] = []
    current: list[tuple[str | None, str]] = []
    current_tokens = 0
    sequence = 0

    def emit() -> None:
        nonlocal current, current_tokens, sequence
        if not current:
            return
        section = next((section for section, _ in current if section), None)
        chunk_text = "\n\n".join(value for _, value in current)
        chunks.append(
            Chunk(
                chunk_id=f"{source_record_id}:{sequence}",
                source_record_id=source_record_id,
                section=section,
                text=chunk_text,
                token_estimate=estimate_tokens(chunk_text),
                sequence=sequence,
            )
        )
        sequence += 1
        current = []
        current_tokens = 0

    for section, block in blocks:
        pieces = _split_oversized(block, target_tokens)
        for piece in pieces:
            piece_tokens = estimate_tokens(piece)
            if current and current_tokens + piece_tokens > target_tokens:
                emit()
            current.append((section, piece))
            current_tokens += piece_tokens
            if current_tokens >= target_tokens:
                emit()
    emit()
    return chunks


def _blocks(text: str) -> list[tuple[str | None, str]]:
    blocks: list[tuple[str | None, str]] = []
    section: str | None = None
    paragraph: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if paragraph:
                blocks.append((section, " ".join(paragraph)))
                paragraph = []
            continue
        if re.match(r"^#{1,6}\s+", stripped):
            if paragraph:
                blocks.append((section, " ".join(paragraph)))
                paragraph = []
            section = re.sub(r"^#{1,6}\s+", "", stripped).strip() or None
            continue
        paragraph.append(stripped)
    if paragraph:
        blocks.append((section, " ".join(paragraph)))
    return blocks


def _split_oversized(text: str, target_tokens: int) -> list[str]:
    if estimate_tokens(text) <= target_tokens:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in sentences:
        if not sentence:
            continue
        sentence_tokens = estimate_tokens(sentence)
        if current and current_tokens + sentence_tokens > target_tokens:
            pieces.append(" ".join(current))
            current = []
            current_tokens = 0
        if sentence_tokens > target_tokens:
            for start in range(0, len(sentence), target_tokens * 4):
                pieces.append(sentence[start : start + target_tokens * 4])
        else:
            current.append(sentence)
            current_tokens += sentence_tokens
    if current:
        pieces.append(" ".join(current))
    return pieces
