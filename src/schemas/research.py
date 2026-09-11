"""Validated schema for research paper ingestion."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from src.schemas.common import CanonicalRecord


class ResearchPaperContent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    title: str = Field(min_length=1, max_length=2_000)
    authors: list[str] = Field(default_factory=list)
    paper_url: AnyHttpUrl
    github_url: AnyHttpUrl | None = None
    github_stars: int | None = Field(default=None, ge=0)
    published_date: datetime
    abstract: str | None = Field(default=None, max_length=100_000)

    @field_validator("published_date")
    @classmethod
    def published_date_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("published_date must include a timezone")
        return value

    @model_validator(mode="after")
    def github_metric_requires_repository(self) -> "ResearchPaperContent":
        if self.github_stars is not None and self.github_url is None:
            raise ValueError("github_stars is only valid when github_url is present")
        return self


class ResearchPaperRecord(CanonicalRecord):
    record_type: Literal["RESEARCH_PAPER"] = Field(alias="recordType")
    content: ResearchPaperContent
