"""GitHub REST client for source-verifiable repository metadata and stars."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlsplit

from src.config.settings import GitHubSettings
from src.fetch.http_client import AsyncHttpClient, RawResponse


class GitHubMetadataError(ValueError):
    """GitHub response lacks the fields needed for a verified repository metric."""


@dataclass(frozen=True, slots=True)
class GitHubRepository:
    normalized_url: str
    full_name: str
    stars: int
    fetched_at: datetime
    raw_response: RawResponse


class GitHubClient:
    """One-run, single-flight cache keyed by canonical GitHub repository URL."""

    def __init__(self, settings: GitHubSettings, http_client: AsyncHttpClient) -> None:
        self._api_base_url = settings.api_base_url.rstrip("/")
        self._http_client = http_client
        self._headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": settings.api_version,
        }
        if settings.token:
            self._headers["Authorization"] = f"Bearer {settings.token}"
        self._cache: dict[str, GitHubRepository] = {}
        self._in_flight: dict[str, asyncio.Task[GitHubRepository]] = {}
        self._lock = asyncio.Lock()

    async def get_repository(self, repository_url: str) -> GitHubRepository:
        normalized_url = normalize_github_repository_url(repository_url)
        async with self._lock:
            cached = self._cache.get(normalized_url)
            if cached is not None:
                return cached
            task = self._in_flight.get(normalized_url)
            if task is None:
                task = asyncio.create_task(self._fetch_repository(normalized_url))
                self._in_flight[normalized_url] = task

        try:
            metadata = await task
        except Exception:
            async with self._lock:
                self._in_flight.pop(normalized_url, None)
            raise

        async with self._lock:
            self._cache[normalized_url] = metadata
            self._in_flight.pop(normalized_url, None)
        return metadata

    async def _fetch_repository(self, normalized_url: str) -> GitHubRepository:
        owner, repository = github_owner_and_repository(normalized_url)
        endpoint = f"{self._api_base_url}/repos/{quote(owner, safe='')}/{quote(repository, safe='')}"
        response = await self._http_client.fetch(endpoint, headers=self._headers)
        try:
            payload = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubMetadataError("GitHub repository response is not JSON") from exc
        if not isinstance(payload, dict):
            raise GitHubMetadataError("GitHub repository response must be an object")
        stars = payload.get("stargazers_count")
        full_name = payload.get("full_name")
        if not isinstance(stars, int) or stars < 0 or not isinstance(full_name, str) or not full_name:
            raise GitHubMetadataError("GitHub repository response lacks verified stargazers_count")
        return GitHubRepository(
            normalized_url=normalized_url,
            full_name=full_name,
            stars=stars,
            fetched_at=response.retrieved_at,
            raw_response=response,
        )


def normalize_github_repository_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "github.com",
        "www.github.com",
    } or parsed.username is not None or parsed.password is not None or parsed.port not in {None, 80, 443}:
        raise ValueError(f"Expected a public GitHub repository URL, got {url!r}")
    components = [component for component in parsed.path.split("/") if component]
    if len(components) != 2:
        raise ValueError(f"GitHub URL does not identify an owner and repository: {url!r}")
    owner, repository = components[:2]
    if repository.endswith(".git"):
        repository = repository[:-4]
    if not owner or not repository:
        raise ValueError(f"GitHub URL does not identify an owner and repository: {url!r}")
    return f"https://github.com/{owner.lower()}/{repository.lower()}"


def github_owner_and_repository(normalized_url: str) -> tuple[str, str]:
    components = [component for component in urlsplit(normalized_url).path.split("/") if component]
    if len(components) != 2:  # defensive: normalized URLs are produced above
        raise ValueError(f"Unexpected normalized GitHub URL: {normalized_url!r}")
    return components[0], components[1]
