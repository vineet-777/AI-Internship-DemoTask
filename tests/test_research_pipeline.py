from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from src.config.settings import ArxivSourceSettings, GitHubSettings, PapersWithCodeSourceSettings
from src.crawlers.research.arxiv import ArxivAtomAdapter, ArxivMetadataClient
from src.crawlers.research.github import GitHubClient, normalize_github_repository_url
from src.crawlers.research.papers_with_code import PapersWithCodeAdapter
from src.fetch.http_client import AsyncHttpClient
from src.fetch.retry import RetryPolicy
from src.jobs.research_ingestion import ResearchIngestionJob
from src.schemas.research import ResearchPaperRecord
from src.storage.base import PersistenceResult
from src.storage.object_store import LocalRawStore, RawDocument


class RecordingRepository:
    """A repository test double; PostgreSQL owns production duplicate enforcement."""

    def __init__(self) -> None:
        self.records: dict[str, ResearchPaperRecord] = {}
        self.raw_documents: dict[str, RawDocument] = {}

    async def upsert(
        self,
        record: ResearchPaperRecord,
        raw_documents: list[RawDocument],
        *,
        source_id: str,
    ) -> PersistenceResult:
        assert source_id in {"arxiv", "papers_with_code"}
        for raw_document in raw_documents:
            self.raw_documents[raw_document.raw_document_id] = raw_document
        if record.record_id in self.records:
            return PersistenceResult(record_id=record.record_id, inserted=False)
        self.records[record.record_id] = record
        return PersistenceResult(record_id=record.record_id, inserted=True)


def test_github_repository_url_normalization_removes_transport_noise() -> None:
    assert (
        normalize_github_repository_url(
            "HTTPS://WWW.GITHUB.COM/Example/Repository.git/?utm_source=feed#readme"
        )
        == "https://github.com/example/repository"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/example/repository/issues",
        "https://user:password@github.com/example/repository",
        "https://github.com:8443/example/repository",
    ],
)
def test_github_repository_url_normalization_rejects_non_repository_urls(url: str) -> None:
    with pytest.raises(ValueError):
        normalize_github_repository_url(url)


async def test_research_slice_preserves_raw_content_and_blocks_duplicate_records(
    tmp_path: Path, arxiv_xml: bytes
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://export.arxiv.org/api/query?id_list=1706.03762"
        return httpx.Response(
            200,
            content=arxiv_xml,
            headers={"content-type": "application/atom+xml; charset=utf-8"},
        )

    repository = RecordingRepository()
    async with AsyncHttpClient(
        timeout_seconds=1,
        connect_timeout_seconds=1,
        max_concurrency=2,
        retry_policy=RetryPolicy(1, 0, 0, 0),
        user_agent="test-agent",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        adapter = ArxivAtomAdapter(
            ArxivSourceSettings(
                id="arxiv",
                name="arXiv",
                endpoint="https://export.arxiv.org/api/query?id_list=1706.03762",
                metadata_endpoint_template="https://export.arxiv.org/api/query?id_list={arxiv_id}",
                enabled=True,
            ),
            http_client,
        )
        job = ResearchIngestionJob(
            adapter=adapter,
            raw_store=LocalRawStore(tmp_path / "raw"),
            repository=repository,
        )
        first_run = await job.run()
        second_run = await job.run()

    assert first_run.discovered_urls == 1
    assert first_run.parsed_records == 1
    assert first_run.inserted_records == 1
    assert second_run.inserted_records == 0
    assert second_run.duplicates_prevented == 1
    assert len(repository.records) == 1

    record = next(iter(repository.records.values()))
    raw_document = next(iter(repository.raw_documents.values()))
    assert record.content.title == "Attention Is All You Need"
    assert str(record.source.url) == "http://arxiv.org/abs/1706.03762v3"
    assert str(record.source.canonical_url) == "https://arxiv.org/abs/1706.03762"
    assert raw_document.content_hash == record.provenance.content_hash
    assert await LocalRawStore(tmp_path / "raw").read_bytes(raw_document) == arxiv_xml
    assert (tmp_path / "raw" / raw_document.storage_key).is_file()


async def test_github_repository_cache_coalesces_normalized_urls() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert str(request.url) == "https://api.github.test/repos/example/repository"
        return httpx.Response(
            200,
            json={"full_name": "example/repository", "stargazers_count": 123},
            headers={"content-type": "application/json"},
        )

    async with AsyncHttpClient(
        timeout_seconds=1,
        connect_timeout_seconds=1,
        max_concurrency=2,
        retry_policy=RetryPolicy(1, 0, 0, 0),
        user_agent="test-agent",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        github = GitHubClient(
            GitHubSettings(
                api_base_url="https://api.github.test",
                api_version="test-version",
                token=None,
            ),
            http_client,
        )
        first, second = await asyncio.gather(
            github.get_repository("https://github.com/Example/Repository"),
            github.get_repository("https://www.github.com/example/repository.git"),
        )

    assert calls == 1
    assert first.stars == second.stars == 123
    assert first.normalized_url == "https://github.com/example/repository"


async def test_pwc_record_is_hydrated_and_enriched_with_verified_github_stars(
    tmp_path: Path, arxiv_xml: bytes
) -> None:
    pwc_payload = {
        "rows": [
            {
                "row": {
                    "paper_url": "https://paperswithcode.com/paper/attention-is-all-you-need",
                    "paper_title": "Attention Is All You Need",
                    "paper_arxiv_id": "1706.03762",
                    "paper_url_abs": "https://arxiv.org/abs/1706.03762v3",
                    "repo_url": "https://github.com/Example/Repository",
                    "is_official": True,
                    "mentioned_in_paper": True,
                    "mentioned_in_github": False,
                    "framework": "tensorflow",
                }
            }
        ]
    }
    github_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal github_calls
        url = str(request.url)
        if url.startswith("https://datasets-server.huggingface.co/rows"):
            return httpx.Response(200, json=pwc_payload)
        if url == "https://export.arxiv.org/api/query?id_list=1706.03762":
            return httpx.Response(
                200,
                content=arxiv_xml,
                headers={"content-type": "application/atom+xml"},
            )
        if url == "https://api.github.test/repos/example/repository":
            github_calls += 1
            return httpx.Response(
                200,
                json={"full_name": "example/repository", "stargazers_count": 123},
            )
        raise AssertionError(f"Unexpected request: {url}")

    repository = RecordingRepository()
    async with AsyncHttpClient(
        timeout_seconds=1,
        connect_timeout_seconds=1,
        max_concurrency=2,
        retry_policy=RetryPolicy(1, 0, 0, 0),
        user_agent="test-agent",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        job = ResearchIngestionJob(
            adapter=PapersWithCodeAdapter(
                PapersWithCodeSourceSettings(
                    id="papers_with_code",
                    name="Papers with Code archive",
                    links_endpoint_template=(
                        "https://datasets-server.huggingface.co/rows?offset={offset}&length={length}"
                    ),
                    batch_size=1,
                    max_records=1,
                    require_official_implementation=True,
                    enabled=True,
                ),
                http_client,
            ),
            raw_store=LocalRawStore(tmp_path / "raw"),
            repository=repository,
            arxiv_metadata_client=ArxivMetadataClient(
                endpoint_template="https://export.arxiv.org/api/query?id_list={arxiv_id}",
                http_client=http_client,
            ),
            github_client=GitHubClient(
                GitHubSettings("https://api.github.test", "test-version", None),
                http_client,
            ),
        )
        summary = await job.run()

    assert summary.inserted_records == 1
    assert summary.rejected_records == 0
    assert github_calls == 1
    record = next(iter(repository.records.values()))
    assert str(record.content.github_url) == "https://github.com/example/repository"
    assert record.content.github_stars == 123
    assert record.provenance.extraction_metadata["implementation_is_official"] is True
    assert len(record.provenance.extraction_metadata["raw_document_ids"]) == 3
    assert len(repository.raw_documents) == 3
