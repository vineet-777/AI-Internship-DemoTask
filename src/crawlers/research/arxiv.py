"""Deterministic parser for the arXiv Atom API's research-paper metadata."""

from __future__ import annotations

from datetime import datetime
from xml.etree import ElementTree

from src.config.settings import ArxivSourceSettings
from src.crawlers.base import SourceAdapter
from src.crawlers.research.models import ResearchPaperCandidate
from src.fetch.http_client import AsyncHttpClient, RawResponse
from src.parsing.identity import canonicalize_arxiv_url

ATOM = "{http://www.w3.org/2005/Atom}"


class SourceParseError(ValueError):
    """Source content is syntactically valid transport data but unusable evidence."""


class ArxivAtomAdapter(SourceAdapter[ResearchPaperCandidate]):
    """Fetch a configured arXiv API query and parse its Atom entries."""

    def __init__(self, settings: ArxivSourceSettings, http_client: AsyncHttpClient) -> None:
        self.source_id = settings.id
        self.source_name = settings.name
        self._endpoint = settings.endpoint
        self._batch_size = getattr(settings, "batch_size", 100)
        self._max_records = getattr(settings, "max_records", 1000)
        self._http_client = http_client

    async def discover(self) -> list[str]:
        if "{start}" in self._endpoint and "{max_results}" in self._endpoint:
            return [
                self._endpoint.format(start=offset, max_results=self._batch_size)
                for offset in range(0, self._max_records, self._batch_size)
            ]
        return [self._endpoint]

    async def fetch(self, url: str) -> RawResponse:
        return await self._http_client.fetch(url)

    def parse(self, response: RawResponse) -> list[ResearchPaperCandidate]:
        return parse_arxiv_atom(response)


class ArxivMetadataClient:
    """Fetch source-evidenced bibliographic metadata for a PWC-linked arXiv paper."""

    def __init__(
        self,
        *,
        endpoint_template: str,
        http_client: AsyncHttpClient,
    ) -> None:
        if "{arxiv_id}" not in endpoint_template:
            raise ValueError("arXiv metadata endpoint must contain an {arxiv_id} placeholder")
        self._endpoint_template = endpoint_template
        self._http_client = http_client

    async def fetch_by_id(self, arxiv_id: str) -> tuple[ResearchPaperCandidate, RawResponse]:
        response = await self._http_client.fetch(
            self._endpoint_template.format(arxiv_id=arxiv_id)
        )
        candidates = parse_arxiv_atom(response)
        if len(candidates) != 1:
            raise SourceParseError(
                f"Expected one arXiv paper for {arxiv_id!r}, received {len(candidates)}"
            )
        return candidates[0], response


def parse_arxiv_atom(response: RawResponse) -> list[ResearchPaperCandidate]:
    try:
        root = ElementTree.fromstring(response.body)
    except ElementTree.ParseError as exc:
        raise SourceParseError("arXiv response is not valid Atom XML") from exc

    candidates: list[ResearchPaperCandidate] = []
    for entry in root.findall(f"{ATOM}entry"):
        source_url = _required_text(entry, f"{ATOM}id")
        published_text = _required_text(entry, f"{ATOM}published")
        try:
            published_at = datetime.fromisoformat(published_text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SourceParseError(f"Invalid arXiv published timestamp: {published_text!r}") from exc
        authors = [
            _required_text(author, f"{ATOM}name")
            for author in entry.findall(f"{ATOM}author")
        ]
        canonical_url = canonicalize_arxiv_url(source_url)
        candidates.append(
            ResearchPaperCandidate(
                original_url=source_url,
                canonical_url=canonical_url,
                paper_url=canonical_url,
                title=" ".join(_required_text(entry, f"{ATOM}title").split()),
                authors=authors,
                published_at=published_at,
                abstract=_optional_text(entry, f"{ATOM}summary"),
                source_metadata={"parser": "arxiv_atom_v1"},
            )
        )
    if not candidates:
        raise SourceParseError("arXiv response contained no paper entries")
    return candidates


def _required_text(element: ElementTree.Element, path: str) -> str:
    value = _optional_text(element, path)
    if not value:
        raise SourceParseError(f"Missing required Atom field {path}")
    return value


def _optional_text(element: ElementTree.Element, path: str) -> str | None:
    child = element.find(path)
    if child is None or child.text is None:
        return None
    value = " ".join(child.text.split())
    return value or None
