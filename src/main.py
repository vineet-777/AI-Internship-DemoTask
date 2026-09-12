"""Command-line entry point for the complete AI Intelligence Ingestion Pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.config.settings import (
    load_arxiv_source,
    load_directory_sources,
    load_feed_sources,
    load_papers_with_code_source,
    load_settings,
)
from src.crawlers.jobs.base import RSSJobAdapter
from src.crawlers.news.base import RSSNewsAdapter
from src.crawlers.product.producthunt import ProductHuntAdapter, ProductHuntSourceSettings
from src.crawlers.product.theres_an_ai import TheresAnAiAdapter, TheresAnAiSettings
from src.crawlers.research.arxiv import ArxivAtomAdapter, ArxivMetadataClient
from src.crawlers.research.github import GitHubClient
from src.crawlers.research.papers_with_code import PapersWithCodeAdapter
from src.crawlers.startup.ycombinator import YCombinatorAdapter, YCombinatorSourceSettings
from src.entities.aliases import AliasTable
from src.entities.mapping_store import MappingStore
from src.entities.matcher import EntityMatcher
from src.export.csv import CsvExporter
from src.export.sheets import GoogleSheetsExporter, PostgresExportSource
from src.extraction.pipeline_extractor import build_pipeline_orchestrator
from src.fetch.http_client import AsyncHttpClient
from src.fetch.rate_limiter import TokenBucketRateLimiter
from src.fetch.retry import RetryPolicy
from src.freshness.watermark import WatermarkStore
from src.jobs.freshness_ingestion import FreshnessIngestionJob
from src.jobs.freshness_persistence import FreshnessPersistenceSink
from src.jobs.product_ingestion import ProductIngestionJob
from src.jobs.research_ingestion import ResearchIngestionJob
from src.jobs.startup_ingestion import StartupIngestionJob
from src.observability.logging import configure_logging
from src.storage.local import LocalIntelligenceRepository
from src.storage.object_store import LocalRawStore
from src.storage.postgres import PostgresResearchRepository

logger = logging.getLogger(__name__)


def _create_http_client(settings: Any) -> AsyncHttpClient:
    retry_policy = RetryPolicy(
        max_attempts=settings.crawler.max_retries,
        base_delay_seconds=settings.crawler.retry_base_delay_seconds,
        max_delay_seconds=settings.crawler.retry_max_delay_seconds,
        jitter_seconds=settings.crawler.retry_jitter_seconds,
    )
    return AsyncHttpClient(
        timeout_seconds=settings.crawler.request_timeout_seconds,
        connect_timeout_seconds=settings.crawler.connect_timeout_seconds,
        max_concurrency=settings.crawler.max_concurrency,
        retry_policy=retry_policy,
        user_agent=settings.crawler.user_agent,
        rate_limiter=TokenBucketRateLimiter(
            settings.crawler.rate_limit_per_second,
            settings.crawler.rate_limit_burst,
        ),
    )


async def _get_repository(settings: Any) -> Any:
    db_url = settings.storage.database_url or os.environ.get("DATABASE_URL")
    if db_url:
        try:
            repo = PostgresResearchRepository(db_url)
            await repo.open()
            return repo
        except Exception as exc:
            logger.warning("Could not connect to PostgreSQL (%s). Falling back to LocalIntelligenceRepository.", exc)
    return LocalIntelligenceRepository()


async def run_arxiv_slice(config_path: Path, sources_path: Path) -> None:
    settings = load_settings(config_path)
    source = load_arxiv_source(sources_path)
    if not source.enabled:
        raise RuntimeError("The configured arXiv source is disabled")

    async with _create_http_client(settings) as http_client:
        repo = await _get_repository(settings)
        try:
            job = ResearchIngestionJob(
                adapter=ArxivAtomAdapter(source, http_client),
                raw_store=LocalRawStore(settings.storage.raw_root),
                repository=repo,
            )
            summary = await job.run()
            print(json.dumps(asdict(summary), indent=2, sort_keys=True))
        finally:
            await repo.close()


async def run_papers_with_code(config_path: Path, sources_path: Path) -> None:
    settings = load_settings(config_path)
    arxiv_source = load_arxiv_source(sources_path)
    source = load_papers_with_code_source(sources_path)
    if not source.enabled:
        raise RuntimeError("The configured Papers with Code source is disabled")

    async with _create_http_client(settings) as http_client:
        repo = await _get_repository(settings)
        try:
            job = ResearchIngestionJob(
                adapter=PapersWithCodeAdapter(source, http_client),
                raw_store=LocalRawStore(settings.storage.raw_root),
                repository=repo,
                arxiv_metadata_client=ArxivMetadataClient(
                    endpoint_template=arxiv_source.metadata_endpoint_template,
                    http_client=http_client,
                ),
                github_client=GitHubClient(settings.github, http_client),
            )
            summary = await job.run()
            print(json.dumps(asdict(summary), indent=2, sort_keys=True))
        finally:
            await repo.close()


async def run_startups(config_path: Path, sources_path: Path) -> None:
    settings = load_settings(config_path)
    sources = load_directory_sources("startup", sources_path)
    if not sources:
        raise RuntimeError("No enabled startup sources found in configs/sources.yaml")

    seed_file = Path("data/normalized/startup_entities.json")
    aliases = AliasTable.from_seed_file(seed_file) if seed_file.exists() else AliasTable()
    matcher = EntityMatcher(aliases)
    mapping_store = MappingStore(Path("data/normalized/entity_mapping_log.jsonl"))
    orchestrator = build_pipeline_orchestrator()

    async with _create_http_client(settings) as http_client:
        repo = await _get_repository(settings)
        try:
            total_discovered = total_parsed = total_inserted = total_dupes = 0
            for src in sources:
                if src.id == "ycombinator":
                    adapter = YCombinatorAdapter(
                        YCombinatorSourceSettings(
                            id=src.id,
                            name=src.name,
                            listing_url=src.listing_url,
                            page_size=src.page_size,
                            max_records=src.max_records,
                            enabled=src.enabled,
                        ),
                        http_client,
                    )
                    job = StartupIngestionJob(
                        adapter=adapter,
                        raw_store=LocalRawStore(settings.storage.raw_root),
                        repository=repo,
                        entity_matcher=matcher,
                        mapping_store=mapping_store,
                        llm_orchestrator=orchestrator,
                    )
                    summary = await job.run()
                    total_discovered += summary.discovered_urls
                    total_parsed += summary.parsed_records
                    total_inserted += summary.inserted_records
                    total_dupes += summary.duplicates_prevented

            print(json.dumps({
                "source": "startups",
                "discovered_urls": total_discovered,
                "parsed_records": total_parsed,
                "inserted_records": total_inserted,
                "duplicates_prevented": total_dupes,
            }, indent=2))
        finally:
            await repo.close()


async def run_products(config_path: Path, sources_path: Path) -> None:
    settings = load_settings(config_path)
    sources = load_directory_sources("product", sources_path)
    if not sources:
        raise RuntimeError("No enabled product sources found in configs/sources.yaml")

    seed_file = Path("data/normalized/startup_entities.json")
    aliases = AliasTable.from_seed_file(seed_file) if seed_file.exists() else AliasTable()
    matcher = EntityMatcher(aliases)
    mapping_store = MappingStore(Path("data/normalized/entity_mapping_log.jsonl"))
    orchestrator = build_pipeline_orchestrator()

    async with _create_http_client(settings) as http_client:
        repo = await _get_repository(settings)
        try:
            total_discovered = total_parsed = total_inserted = total_dupes = 0
            for src in sources:
                if src.id == "product_hunt":
                    adapter = ProductHuntAdapter(
                        ProductHuntSourceSettings(
                            id=src.id,
                            name=src.name,
                            listing_url=src.listing_url,
                            page_size=src.page_size,
                            max_records=src.max_records,
                            enabled=src.enabled,
                        ),
                        http_client,
                    )
                elif src.id == "theres_an_ai_for_that":
                    adapter = TheresAnAiAdapter(
                        TheresAnAiSettings(
                            id=src.id,
                            name=src.name,
                            listing_url=src.listing_url,
                            page_size=src.page_size,
                            max_records=src.max_records,
                            enabled=src.enabled,
                        ),
                        http_client,
                    )
                else:
                    continue

                job = ProductIngestionJob(
                    adapter=adapter,
                    raw_store=LocalRawStore(settings.storage.raw_root),
                    repository=repo,
                    entity_matcher=matcher,
                    mapping_store=mapping_store,
                    llm_orchestrator=orchestrator,
                )
                summary = await job.run()
                total_discovered += summary.discovered_urls
                total_parsed += summary.parsed_records
                total_inserted += summary.inserted_records
                total_dupes += summary.duplicates_prevented

            print(json.dumps({
                "source": "products",
                "discovered_urls": total_discovered,
                "parsed_records": total_parsed,
                "inserted_records": total_inserted,
                "duplicates_prevented": total_dupes,
            }, indent=2))
        finally:
            await repo.close()


async def run_news(config_path: Path, sources_path: Path) -> None:
    settings = load_settings(config_path)
    sources = load_feed_sources("news", sources_path)
    if not sources:
        raise RuntimeError("No enabled news sources found in configs/sources.yaml")

    orchestrator = build_pipeline_orchestrator()

    async with _create_http_client(settings) as http_client:
        repo = await _get_repository(settings)
        try:
            watermarks = WatermarkStore(Path("data/watermarks/news.json"))
            sink = FreshnessPersistenceSink(repo)
            total_discovered = total_parsed = total_accepted = 0

            for src in sources:
                adapter = RSSNewsAdapter(src.id, src.name, src.feed_url, http_client)
                job = FreshnessIngestionJob(
                    adapter=adapter,
                    watermark_store=watermarks,
                    sink=sink,
                    raw_store=LocalRawStore(settings.storage.raw_root),
                    llm_orchestrator=orchestrator,
                )
                summary = await job.run()
                total_discovered += summary.discovered_urls
                total_parsed += summary.parsed_records
                total_accepted += summary.accepted_records

            print(json.dumps({
                "vertical": "news",
                "sources_monitored": len(sources),
                "discovered_urls": total_discovered,
                "parsed_records": total_parsed,
                "accepted_24h_records": total_accepted,
            }, indent=2))
        finally:
            await repo.close()


async def run_jobs(config_path: Path, sources_path: Path) -> None:
    settings = load_settings(config_path)
    sources = load_feed_sources("job", sources_path)
    if not sources:
        raise RuntimeError("No enabled job sources found in configs/sources.yaml")

    orchestrator = build_pipeline_orchestrator()

    async with _create_http_client(settings) as http_client:
        repo = await _get_repository(settings)
        try:
            watermarks = WatermarkStore(Path("data/watermarks/jobs.json"))
            sink = FreshnessPersistenceSink(repo)
            total_discovered = total_parsed = total_accepted = 0

            for src in sources:
                adapter = RSSJobAdapter(src.id, src.name, src.feed_url, http_client)
                job = FreshnessIngestionJob(
                    adapter=adapter,
                    watermark_store=watermarks,
                    sink=sink,
                    raw_store=LocalRawStore(settings.storage.raw_root),
                    llm_orchestrator=orchestrator,
                )
                summary = await job.run()
                total_discovered += summary.discovered_urls
                total_parsed += summary.parsed_records
                total_accepted += summary.accepted_records

            print(json.dumps({
                "vertical": "jobs",
                "sources_monitored": len(sources),
                "discovered_urls": total_discovered,
                "parsed_records": total_parsed,
                "accepted_24h_records": total_accepted,
            }, indent=2))
        finally:
            await repo.close()


async def run_extract_llm() -> None:
    orchestrator = build_pipeline_orchestrator()
    if orchestrator is None:
        print(json.dumps({
            "status": "skipped",
            "message": "No LLM provider keys set (GEMINI_API_KEY, GROQ_API_KEY, DEEPSEEK_API_KEY).",
        }, indent=2))
        return

    from src.extraction.pipeline_extractor import LLMJobExtraction
    sample_text = "Senior Research Scientist at Anthropic in San Francisco, CA. Remote eligible. Designing scalable alignment protocols."
    result = await orchestrator.extract(sample_text, LLMJobExtraction)
    print(json.dumps({
        "status": "success",
        "provider": result.provider,
        "model": result.model,
        "extracted": result.value.model_dump(),
    }, indent=2))


async def run_export_csv(config_path: Path, output_dir: Path) -> None:
    settings = load_settings(config_path)
    repo = await _get_repository(settings)
    try:
        if isinstance(repo, LocalIntelligenceRepository):
            tabs = repo.read_tabs()
        else:
            export_source = PostgresExportSource(repo._pool)
            tabs = await export_source.read_tabs()

        exporter = CsvExporter(output_dir)
        outputs = exporter.export(tabs)
        summary = {tab: {"path": str(path), "rows": len(tabs.get(tab, []))} for tab, path in outputs.items()}
        print(json.dumps(summary, indent=2))
    finally:
        await repo.close()


async def run_export_sheets(config_path: Path) -> None:
    settings = load_settings(config_path)
    spreadsheet_id = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID")
    access_token = os.environ.get("GOOGLE_SHEETS_ACCESS_TOKEN")

    if not spreadsheet_id or not access_token:
        print(json.dumps({
            "error": "GOOGLE_SHEETS_SPREADSHEET_ID and GOOGLE_SHEETS_ACCESS_TOKEN are required in environment."
        }, indent=2))
        return

    repo = await _get_repository(settings)
    try:
        if isinstance(repo, LocalIntelligenceRepository):
            tabs = repo.read_tabs()
        else:
            export_source = PostgresExportSource(repo._pool)
            tabs = await export_source.read_tabs()

        async with GoogleSheetsExporter(spreadsheet_id, access_token) as exporter:
            await exporter.export(tabs)
        print(json.dumps({"status": "exported", "spreadsheet_id": spreadsheet_id}, indent=2))
    finally:
        await repo.close()


async def run_all(config_path: Path, sources_path: Path, output_dir: Path) -> None:
    print("=== Step 1/6: Ingesting Research Papers (arXiv & Papers with Code) ===")
    try:
        await run_arxiv_slice(config_path, sources_path)
    except Exception as exc:
        logger.error("arXiv step failed: %s", exc)

    try:
        await run_papers_with_code(config_path, sources_path)
    except Exception as exc:
        logger.error("Papers with Code step failed: %s", exc)

    print("\n=== Step 2/6: Ingesting Startups ===")
    try:
        await run_startups(config_path, sources_path)
    except Exception as exc:
        logger.error("Startups step failed: %s", exc)

    print("\n=== Step 3/6: Ingesting Products ===")
    try:
        await run_products(config_path, sources_path)
    except Exception as exc:
        logger.error("Products step failed: %s", exc)

    print("\n=== Step 4/6: Ingesting 24h Fresh News (5 AI Sources) ===")
    try:
        await run_news(config_path, sources_path)
    except Exception as exc:
        logger.error("News step failed: %s", exc)

    print("\n=== Step 5/6: Ingesting 24h Fresh Jobs (5 AI Job Boards) ===")
    try:
        await run_jobs(config_path, sources_path)
    except Exception as exc:
        logger.error("Jobs step failed: %s", exc)

    print("\n=== Step 6/6: Exporting 6 Required Tabs to CSV ===")
    await run_export_csv(config_path, output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Intelligence Ingestion Pipeline Entry Point")
    parser.add_argument(
        "command",
        choices=[
            "ingest-arxiv",
            "ingest-papers-with-code",
            "ingest-startups",
            "ingest-products",
            "ingest-news",
            "ingest-jobs",
            "extract-llm",
            "export-csv",
            "export-sheets",
            "run-all",
        ],
    )
    parser.add_argument("--config", type=Path, default=Path("configs/settings.yaml"))
    parser.add_argument("--sources", type=Path, default=Path("configs/sources.yaml"))
    parser.add_argument("--export-dir", type=Path, default=Path("data/export"))
    arguments = parser.parse_args()
    configure_logging()

    if arguments.command == "ingest-arxiv":
        asyncio.run(run_arxiv_slice(arguments.config, arguments.sources))
    elif arguments.command == "ingest-papers-with-code":
        asyncio.run(run_papers_with_code(arguments.config, arguments.sources))
    elif arguments.command == "ingest-startups":
        asyncio.run(run_startups(arguments.config, arguments.sources))
    elif arguments.command == "ingest-products":
        asyncio.run(run_products(arguments.config, arguments.sources))
    elif arguments.command == "ingest-news":
        asyncio.run(run_news(arguments.config, arguments.sources))
    elif arguments.command == "ingest-jobs":
        asyncio.run(run_jobs(arguments.config, arguments.sources))
    elif arguments.command == "extract-llm":
        asyncio.run(run_extract_llm())
    elif arguments.command == "export-csv":
        asyncio.run(run_export_csv(arguments.config, arguments.export_dir))
    elif arguments.command == "export-sheets":
        asyncio.run(run_export_sheets(arguments.config))
    elif arguments.command == "run-all":
        asyncio.run(run_all(arguments.config, arguments.sources, arguments.export_dir))


if __name__ == "__main__":
    main()
