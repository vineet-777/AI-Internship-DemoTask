"""Tests for source configurations including 5 job feeds, 5 news feeds, and bulk directories."""

from __future__ import annotations

from pathlib import Path

from src.config.settings import (
    load_arxiv_source,
    load_directory_sources,
    load_feed_sources,
    load_papers_with_code_source,
)


def test_sources_configuration() -> None:
    sources_path = Path("configs/sources.yaml")
    assert sources_path.exists()

    # Verify arXiv source
    arxiv = load_arxiv_source(sources_path)
    assert arxiv.enabled is True
    assert arxiv.max_records == 1000
    assert "{start}" in arxiv.endpoint
    assert "{max_results}" in arxiv.endpoint

    # Verify Papers with Code source
    pwc = load_papers_with_code_source(sources_path)
    assert pwc.enabled is True
    assert pwc.max_records == 1000

    # Verify 5 AI news sources
    news_sources = load_feed_sources("news", sources_path)
    assert len(news_sources) == 5
    news_ids = {s.id for s in news_sources}
    assert "techcrunch_ai" in news_ids
    assert "venturebeat_ai" in news_ids
    assert "mit_technology_review_ai" in news_ids
    assert "openai_news" in news_ids
    assert "google_ai_blog" in news_ids

    # Verify 5 AI job boards
    job_sources = load_feed_sources("job", sources_path)
    assert len(job_sources) == 5
    job_ids = {s.id for s in job_sources}
    assert "remoteok_ai" in job_ids
    assert "wework_remotely_ai" in job_ids
    assert "ai_jobs" in job_ids
    assert "himalayas_ai" in job_ids
    assert "jobspresso_ai" in job_ids

    # Verify startup directory sources
    startup_sources = load_directory_sources("startup", sources_path)
    assert len(startup_sources) >= 1
    assert any(s.id == "ycombinator" for s in startup_sources)

    # Verify product directory sources
    product_sources = load_directory_sources("product", sources_path)
    assert len(product_sources) >= 2
    product_ids = {s.id for s in product_sources}
    assert "product_hunt" in product_ids
    assert "theres_an_ai_for_that" in product_ids
