"""Typed application settings loaded from YAML with environment overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class CrawlerSettings:
    max_concurrency: int
    request_timeout_seconds: float
    connect_timeout_seconds: float
    max_retries: int
    retry_base_delay_seconds: float
    retry_max_delay_seconds: float
    retry_jitter_seconds: float
    user_agent: str


@dataclass(frozen=True, slots=True)
class StorageSettings:
    raw_root: Path
    database_url: str | None


@dataclass(frozen=True, slots=True)
class GitHubSettings:
    api_base_url: str
    api_version: str
    token: str | None


@dataclass(frozen=True, slots=True)
class AppSettings:
    crawler: CrawlerSettings
    storage: StorageSettings
    github: GitHubSettings


@dataclass(frozen=True, slots=True)
class ArxivSourceSettings:
    id: str
    name: str
    endpoint: str
    metadata_endpoint_template: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class PapersWithCodeSourceSettings:
    id: str
    name: str
    links_endpoint_template: str
    batch_size: int
    max_records: int
    require_official_implementation: bool
    enabled: bool


def load_settings(path: Path | str = "configs/settings.yaml") -> AppSettings:
    """Load non-secret settings and overlay environment-owned values."""
    document = _load_yaml(Path(path))
    crawler = document["crawler"]
    storage = document["storage"]
    github = document["github"]
    raw_root = Path(os.environ.get("RAW_STORAGE_ROOT", storage["raw_root"]))
    return AppSettings(
        crawler=CrawlerSettings(
            max_concurrency=int(crawler["max_concurrency"]),
            request_timeout_seconds=float(crawler["request_timeout_seconds"]),
            connect_timeout_seconds=float(crawler["connect_timeout_seconds"]),
            max_retries=int(crawler["max_retries"]),
            retry_base_delay_seconds=float(crawler["retry_base_delay_seconds"]),
            retry_max_delay_seconds=float(crawler["retry_max_delay_seconds"]),
            retry_jitter_seconds=float(crawler["retry_jitter_seconds"]),
            user_agent=str(crawler["user_agent"]),
        ),
        storage=StorageSettings(
            raw_root=raw_root,
            database_url=os.environ.get("DATABASE_URL"),
        ),
        github=GitHubSettings(
            api_base_url=str(github["api_base_url"]),
            api_version=str(github["api_version"]),
            token=os.environ.get("GITHUB_TOKEN"),
        ),
    )


def load_arxiv_source(path: Path | str = "configs/sources.yaml") -> ArxivSourceSettings:
    """Load the single source enabled for this milestone."""
    for source in _load_yaml(Path(path)).get("sources", []):
        if source.get("id") == "arxiv":
            return ArxivSourceSettings(
                id=str(source["id"]),
                name=str(source["name"]),
                endpoint=str(source["endpoint"]),
                metadata_endpoint_template=str(source["metadata_endpoint_template"]),
                enabled=bool(source["enabled"]),
            )
    raise ValueError("configs/sources.yaml does not define an arxiv source")


def load_papers_with_code_source(
    path: Path | str = "configs/sources.yaml",
) -> PapersWithCodeSourceSettings:
    """Load the PWC archive source used for repository associations."""
    for source in _load_yaml(Path(path)).get("sources", []):
        if source.get("id") == "papers_with_code":
            return PapersWithCodeSourceSettings(
                id=str(source["id"]),
                name=str(source["name"]),
                links_endpoint_template=str(source["links_endpoint_template"]),
                batch_size=int(source["batch_size"]),
                max_records=int(source["max_records"]),
                require_official_implementation=bool(source["require_official_implementation"]),
                enabled=bool(source["enabled"]),
            )
    raise ValueError("configs/sources.yaml does not define a papers_with_code source")


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    if not isinstance(document, dict):
        raise ValueError(f"Configuration file {path} must contain a mapping")
    return document
