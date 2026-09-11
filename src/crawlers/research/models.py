"""Normalized source candidates before they become canonical research records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ResearchPaperCandidate:
    """Only source-evidenced values; incomplete candidates must be hydrated or rejected."""

    original_url: str
    canonical_url: str
    paper_url: str
    title: str
    authors: list[str]
    published_at: datetime | None
    abstract: str | None
    github_url: str | None = None
    source_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def needs_bibliographic_hydration(self) -> bool:
        return self.published_at is None
