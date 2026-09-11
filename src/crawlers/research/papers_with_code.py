"""Adapter for the official Papers with Code paper-to-repository archive."""

from __future__ import annotations

import json
from typing import Any

from src.config.settings import PapersWithCodeSourceSettings
from src.crawlers.base import SourceAdapter
from src.crawlers.research.models import ResearchPaperCandidate
from src.fetch.http_client import AsyncHttpClient, RawResponse
from src.parsing.identity import canonicalize_arxiv_url, canonicalize_url


class PapersWithCodeParseError(ValueError):
    """The archive response cannot safely be interpreted as source evidence."""


class PapersWithCodeAdapter(SourceAdapter[ResearchPaperCandidate]):
    """Read PWC's official archive, retaining only explicit arXiv/GitHub links."""

    def __init__(
        self,
        settings: PapersWithCodeSourceSettings,
        http_client: AsyncHttpClient,
    ) -> None:
        if settings.batch_size < 1 or settings.max_records < 1:
            raise ValueError("Papers with Code batch_size and max_records must be positive")
        self.source_id = settings.id
        self.source_name = settings.name
        self._endpoint_template = settings.links_endpoint_template
        self._batch_size = settings.batch_size
        self._max_records = settings.max_records
        self._require_official = settings.require_official_implementation
        self._http_client = http_client

    async def discover(self) -> list[str]:
        return [
            self._endpoint_template.format(
                offset=offset,
                length=min(self._batch_size, self._max_records - offset),
            )
            for offset in range(0, self._max_records, self._batch_size)
        ]

    async def fetch(self, url: str) -> RawResponse:
        return await self._http_client.fetch(url)

    def parse(self, response: RawResponse) -> list[ResearchPaperCandidate]:
        try:
            document = json.loads(response.body)
            rows = document["rows"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise PapersWithCodeParseError("PWC archive response has no rows payload") from exc
        if not isinstance(rows, list):
            raise PapersWithCodeParseError("PWC archive rows payload must be a list")

        candidates: list[ResearchPaperCandidate] = []
        for wrapped_row in rows:
            row = wrapped_row.get("row") if isinstance(wrapped_row, dict) else None
            if not isinstance(row, dict):
                continue
            candidate = _candidate_from_row(row, require_official=self._require_official)
            if candidate is not None:
                candidates.append(candidate)
        return candidates


def _candidate_from_row(
    row: dict[str, Any],
    *,
    require_official: bool,
) -> ResearchPaperCandidate | None:
    if require_official and row.get("is_official") is not True:
        return None
    paper_page = _non_empty_string(row.get("paper_url"))
    paper_url_abs = _non_empty_string(row.get("paper_url_abs"))
    repository_url = _non_empty_string(row.get("repo_url"))
    title = _non_empty_string(row.get("paper_title"))
    arxiv_id = _non_empty_string(row.get("paper_arxiv_id"))
    if not all((paper_page, paper_url_abs, repository_url, title, arxiv_id)):
        return None
    try:
        canonical_paper_url = canonicalize_arxiv_url(paper_url_abs)
        canonical_source_url = canonicalize_url(paper_page)
    except ValueError:
        return None

    return ResearchPaperCandidate(
        original_url=paper_page,
        canonical_url=canonical_source_url,
        paper_url=canonical_paper_url,
        title=title,
        authors=[],
        published_at=None,
        abstract=None,
        github_url=repository_url,
        source_metadata={
            "parser": "papers_with_code_archive_rows_v1",
            "paper_arxiv_id": arxiv_id,
            "implementation_is_official": bool(row.get("is_official")),
            "implementation_mentioned_in_paper": bool(row.get("mentioned_in_paper")),
            "implementation_mentioned_in_github": bool(row.get("mentioned_in_github")),
            "implementation_framework": _non_empty_string(row.get("framework")),
        },
    )


def _non_empty_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized or None
