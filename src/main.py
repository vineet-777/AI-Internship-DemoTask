"""Command-line entry point for the validated first ingestion slice."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from src.config.settings import load_arxiv_source, load_papers_with_code_source, load_settings
from src.crawlers.research.arxiv import ArxivAtomAdapter, ArxivMetadataClient
from src.crawlers.research.github import GitHubClient
from src.crawlers.research.papers_with_code import PapersWithCodeAdapter
from src.fetch.http_client import AsyncHttpClient
from src.fetch.retry import RetryPolicy
from src.jobs.research_ingestion import ResearchIngestionJob
from src.observability.logging import configure_logging
from src.storage.object_store import LocalRawStore
from src.storage.postgres import PostgresResearchRepository


async def run_arxiv_slice(config_path: Path, sources_path: Path) -> None:
    settings = load_settings(config_path)
    source = load_arxiv_source(sources_path)
    if not source.enabled:
        raise RuntimeError("The configured arXiv source is disabled")
    database_url = settings.storage.database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL is required; copy .env.example or set the environment variable")

    retry_policy = RetryPolicy(
        max_attempts=settings.crawler.max_retries,
        base_delay_seconds=settings.crawler.retry_base_delay_seconds,
        max_delay_seconds=settings.crawler.retry_max_delay_seconds,
        jitter_seconds=settings.crawler.retry_jitter_seconds,
    )
    async with AsyncHttpClient(
        timeout_seconds=settings.crawler.request_timeout_seconds,
        connect_timeout_seconds=settings.crawler.connect_timeout_seconds,
        max_concurrency=settings.crawler.max_concurrency,
        retry_policy=retry_policy,
        user_agent=settings.crawler.user_agent,
    ) as http_client:
        async with PostgresResearchRepository(database_url) as repository:
            job = ResearchIngestionJob(
                adapter=ArxivAtomAdapter(source, http_client),
                raw_store=LocalRawStore(settings.storage.raw_root),
                repository=repository,
            )
            summary = await job.run()
    print(json.dumps(asdict(summary), indent=2, sort_keys=True))


async def run_papers_with_code(config_path: Path, sources_path: Path) -> None:
    settings = load_settings(config_path)
    arxiv_source = load_arxiv_source(sources_path)
    source = load_papers_with_code_source(sources_path)
    if not source.enabled:
        raise RuntimeError("The configured Papers with Code source is disabled")
    database_url = settings.storage.database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL is required; use the .env.example value template")

    retry_policy = RetryPolicy(
        max_attempts=settings.crawler.max_retries,
        base_delay_seconds=settings.crawler.retry_base_delay_seconds,
        max_delay_seconds=settings.crawler.retry_max_delay_seconds,
        jitter_seconds=settings.crawler.retry_jitter_seconds,
    )
    async with AsyncHttpClient(
        timeout_seconds=settings.crawler.request_timeout_seconds,
        connect_timeout_seconds=settings.crawler.connect_timeout_seconds,
        max_concurrency=settings.crawler.max_concurrency,
        retry_policy=retry_policy,
        user_agent=settings.crawler.user_agent,
    ) as http_client:
        async with PostgresResearchRepository(database_url) as repository:
            job = ResearchIngestionJob(
                adapter=PapersWithCodeAdapter(source, http_client),
                raw_store=LocalRawStore(settings.storage.raw_root),
                repository=repository,
                arxiv_metadata_client=ArxivMetadataClient(
                    endpoint_template=arxiv_source.metadata_endpoint_template,
                    http_client=http_client,
                ),
                github_client=GitHubClient(settings.github, http_client),
            )
            summary = await job.run()
    print(json.dumps(asdict(summary), indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the first arXiv research ingestion slice")
    parser.add_argument("command", choices=["ingest-arxiv", "ingest-papers-with-code"])
    parser.add_argument("--config", type=Path, default=Path("configs/settings.yaml"))
    parser.add_argument("--sources", type=Path, default=Path("configs/sources.yaml"))
    arguments = parser.parse_args()
    configure_logging()
    if arguments.command == "ingest-arxiv":
        asyncio.run(run_arxiv_slice(arguments.config, arguments.sources))
    if arguments.command == "ingest-papers-with-code":
        asyncio.run(run_papers_with_code(arguments.config, arguments.sources))


if __name__ == "__main__":
    main()
