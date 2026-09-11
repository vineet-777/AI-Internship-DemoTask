from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.schemas.research import ResearchPaperContent


def test_research_content_accepts_source_evidenced_values() -> None:
    content = ResearchPaperContent(
        title="Attention Is All You Need",
        authors=["Ashish Vaswani"],
        paper_url="https://arxiv.org/abs/1706.03762",
        published_date=datetime(2017, 6, 12, 17, 57, 34, tzinfo=UTC),
    )

    assert content.github_url is None
    assert content.github_stars is None


def test_research_content_rejects_unsupported_github_metric() -> None:
    with pytest.raises(ValidationError, match="github_stars"):
        ResearchPaperContent(
            title="A paper",
            authors=[],
            paper_url="https://arxiv.org/abs/1706.03762",
            github_stars=42,
            published_date=datetime(2017, 6, 12, tzinfo=UTC),
        )
