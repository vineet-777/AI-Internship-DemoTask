"""Tests for full-text and publication date extraction."""

from __future__ import annotations

from datetime import UTC, datetime

from src.parsing.full_text import extract_full_text


def test_extract_full_text_with_json_ld() -> None:
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>OpenAI Releases GPT-5</title>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": "OpenAI Releases GPT-5",
            "datePublished": "2026-08-15T14:30:00Z",
            "author": {"@type": "Person", "name": "Sam Altman"}
        }
        </script>
    </head>
    <body>
        <nav><a href="/">Home</a></nav>
        <article>
            <h1>OpenAI Releases GPT-5</h1>
            <p>Today OpenAI announced the general availability of GPT-5 with revolutionary reasoning and agentic multimodal intelligence.</p>
            <p>The system features an autonomous planning engine and near-zero latency execution across frontier benchmarks.</p>
        </article>
        <footer>Copyright 2026</footer>
    </body>
    </html>
    """
    extracted = extract_full_text(html)
    assert extracted.title == "OpenAI Releases GPT-5"
    assert "Today OpenAI announced" in extracted.body
    assert "revolutionary reasoning" in extracted.body
    assert "Copyright" not in extracted.body
    assert extracted.published_date == datetime(2026, 8, 15, 14, 30, tzinfo=UTC)
    assert extracted.date_source == "json_ld"
    assert extracted.date_confidence == 0.95
    assert extracted.author == "Sam Altman"


def test_extract_full_text_with_meta_tags() -> None:
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta property="article:published_time" content="2026-09-01T10:00:00+00:00">
        <meta name="author" content="Tech Reporter">
    </head>
    <body>
        <main>
            <p>Artificial Intelligence infrastructure has scaled significantly over the past quarter.</p>
            <p>Data centers are deploying next-generation optical interconnects for distributed cluster training.</p>
        </main>
    </body>
    </html>
    """
    extracted = extract_full_text(html)
    assert "Artificial Intelligence infrastructure" in extracted.body
    assert extracted.published_date == datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    assert extracted.date_source == "meta"
    assert extracted.author == "Tech Reporter"


def test_extract_full_text_fallback_description() -> None:
    html = "<html><body>Empty</body></html>"
    extracted = extract_full_text(html, fallback_description="Fallback article body text")
    assert extracted.body == "Fallback article body text"
