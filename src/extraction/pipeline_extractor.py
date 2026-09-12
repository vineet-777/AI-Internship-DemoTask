"""Runtime LLM pipeline extraction bridge connecting orchestrator to ingestion jobs."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from src.config.settings import LLMProviderConfig, load_llm_configs
from src.crawlers.jobs.base import JobCandidate
from src.crawlers.news.base import NewsCandidate
from src.crawlers.product.base import ProductCandidate
from src.crawlers.startup.base import StartupCandidate
from src.extraction.orchestrator import LLMOrchestrator
from src.extraction.providers.base import LLMProvider
from src.extraction.providers.deepseek import DeepSeekProvider
from src.extraction.providers.gemini import GeminiProvider
from src.extraction.providers.groq import GroqProvider

logger = logging.getLogger(__name__)


class LLMJobExtraction(BaseModel):
    company: str | None = Field(default=None, description="Company name hiring for the job")
    is_remote: bool = Field(default=False, description="Whether the job is remote")
    role_family: str | None = Field(default=None, description="Role family: Engineering, Research, Product, Design, Sales, Marketing")


class LLMNewsExtraction(BaseModel):
    summary: str | None = Field(default=None, description="Concise 2-sentence summary of the news")
    category: str = Field(default="AI", description="Primary category: AI, Robotics, Hardware, LLM, Policy")
    primary_entity: str | None = Field(default=None, description="Primary company or startup mentioned")


class LLMStartupExtraction(BaseModel):
    employee_count: int | None = Field(default=None, description="Estimated or stated employee count")
    headquarters: str | None = Field(default=None, description="City, State/Country headquarters")
    founded_year: int | None = Field(default=None, description="Founding year between 1800 and 2100")


class LLMProductExtraction(BaseModel):
    pricing_model: str = Field(default="FREEMIUM", description="Pricing model: FREE, FREEMIUM, PAID, ENTERPRISE")
    startup_name: str | None = Field(default=None, description="Name of the company or team behind the product")


def build_pipeline_orchestrator(
    configs: list[LLMProviderConfig] | None = None,
) -> LLMOrchestrator | None:
    """Instantiate the multi-tier fallback LLM orchestrator using available API keys."""
    configs = configs or load_llm_configs()
    providers: list[LLMProvider] = []

    for cfg in configs:
        if not cfg.enabled or not cfg.api_key:
            continue
        if cfg.name == "gemini":
            providers.append(
                GeminiProvider(
                    model=cfg.model,
                    api_key=cfg.api_key,
                    endpoint=cfg.endpoint,
                    max_concurrency=cfg.max_concurrency,
                    timeout_seconds=cfg.timeout_seconds,
                )
            )
        elif cfg.name == "groq":
            providers.append(
                GroqProvider(
                    model=cfg.model,
                    api_key=cfg.api_key,
                    endpoint=cfg.endpoint,
                    max_concurrency=cfg.max_concurrency,
                    timeout_seconds=cfg.timeout_seconds,
                )
            )
        elif cfg.name == "deepseek":
            providers.append(
                DeepSeekProvider(
                    model=cfg.model,
                    api_key=cfg.api_key,
                    endpoint=cfg.endpoint,
                    max_concurrency=cfg.max_concurrency,
                    timeout_seconds=cfg.timeout_seconds,
                )
            )

    if not providers:
        logger.info("No LLM provider API keys configured; pipeline will use deterministic parsers.")
        return None

    return LLMOrchestrator(providers)


async def enrich_job_with_llm(
    orchestrator: LLMOrchestrator | None, candidate: JobCandidate
) -> JobCandidate:
    if orchestrator is None:
        return candidate
    try:
        result = await orchestrator.extract(
            f"Title: {candidate.title}\nCompany: {candidate.company}\nDescription: {candidate.description[:2000]}",
            LLMJobExtraction,
            source_record_id=candidate.canonical_url,
        )
        extracted: LLMJobExtraction = result.value  # type: ignore
        return JobCandidate(
            original_url=candidate.original_url,
            canonical_url=candidate.canonical_url,
            company=extracted.company or candidate.company,
            title=candidate.title,
            description=candidate.description,
            published_at=candidate.published_at,
            date_source=candidate.date_source,
            date_confidence=candidate.date_confidence,
            is_remote=extracted.is_remote or candidate.is_remote,
            role_family=extracted.role_family or candidate.role_family,
        )
    except Exception as exc:
        logger.warning("LLM job enrichment failed, keeping deterministic candidate: %s", exc)
        return candidate


async def enrich_news_with_llm(
    orchestrator: LLMOrchestrator | None, candidate: NewsCandidate
) -> NewsCandidate:
    if orchestrator is None:
        return candidate
    try:
        result = await orchestrator.extract(
            f"Title: {candidate.title}\nBody: {candidate.body[:2000]}",
            LLMNewsExtraction,
            source_record_id=candidate.canonical_url,
        )
        extracted: LLMNewsExtraction = result.value  # type: ignore
        return NewsCandidate(
            original_url=candidate.original_url,
            canonical_url=candidate.canonical_url,
            title=candidate.title,
            body=candidate.body,
            author=candidate.author,
            published_at=candidate.published_at,
            date_source=candidate.date_source,
            date_confidence=candidate.date_confidence,
            category=extracted.category or candidate.category,
        )
    except Exception as exc:
        logger.warning("LLM news enrichment failed, keeping deterministic candidate: %s", exc)
        return candidate


async def enrich_startup_with_llm(
    orchestrator: LLMOrchestrator | None, candidate: StartupCandidate
) -> tuple[StartupCandidate, bool]:
    """Enrich a startup candidate with LLM-extracted structured data.

    Returns the enriched candidate and a boolean indicating whether LLM was used.
    """
    if orchestrator is None:
        return candidate, False
    try:
        description = candidate.data.get("description", "") or ""
        text = f"Name: {candidate.entity_name}\nDescription: {description[:2000]}"
        result = await orchestrator.extract(
            text,
            LLMStartupExtraction,
            source_record_id=candidate.canonical_url,
        )
        extracted: LLMStartupExtraction = result.value  # type: ignore
        data = candidate.data.copy()
        if extracted.employee_count is not None and data.get("employeeCount") is None:
            data["employeeCount"] = extracted.employee_count
        if extracted.headquarters is not None and data.get("headquarters") is None:
            data["headquarters"] = extracted.headquarters
        if extracted.founded_year is not None and data.get("foundedYear") is None:
            data["foundedYear"] = extracted.founded_year
        enriched = StartupCandidate(
            original_url=candidate.original_url,
            canonical_url=candidate.canonical_url,
            entity_name=candidate.entity_name,
            data=data,
        )
        return enriched, True
    except Exception as exc:
        logger.warning("LLM startup enrichment failed, keeping deterministic candidate: %s", exc)
        return candidate, False


async def enrich_product_with_llm(
    orchestrator: LLMOrchestrator | None, candidate: ProductCandidate
) -> tuple[ProductCandidate, bool]:
    """Enrich a product candidate with LLM-extracted structured data.

    Returns the enriched candidate and a boolean indicating whether LLM was used.
    """
    if orchestrator is None:
        return candidate, False
    try:
        description = candidate.data.get("description", "") or ""
        text = f"Product: {candidate.product_name}\nStartup: {candidate.startup_name}\nDescription: {description[:2000]}"
        result = await orchestrator.extract(
            text,
            LLMProductExtraction,
            source_record_id=candidate.canonical_url,
        )
        extracted: LLMProductExtraction = result.value  # type: ignore
        data = candidate.data.copy()
        if extracted.startup_name and candidate.startup_name in ("Unknown", "", None):
            startup_name = extracted.startup_name
        else:
            startup_name = candidate.startup_name
        from src.schemas.product import PricingModel
        try:
            pricing = PricingModel(extracted.pricing_model)
        except ValueError:
            pricing = candidate.pricing_model
        enriched = ProductCandidate(
            original_url=candidate.original_url,
            canonical_url=candidate.canonical_url,
            product_name=candidate.product_name,
            startup_name=startup_name,
            pricing_model=pricing,
            data=data,
        )
        return enriched, True
    except Exception as exc:
        logger.warning("LLM product enrichment failed, keeping deterministic candidate: %s", exc)
        return candidate, False
