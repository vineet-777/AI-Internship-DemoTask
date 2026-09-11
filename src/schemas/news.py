"""Canonical schema for fresh news records."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.schemas.common import CanonicalRecord

DateSource = Literal["json_ld", "meta", "time", "source_specific", "rss", "visible", "relative"]


class NewsContent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    title: str = Field(min_length=1, max_length=2_000)
    published_date: datetime = Field(alias="publishedDate")
    author: str | None = Field(default=None, max_length=500)
    body: str = Field(min_length=1, max_length=200_000)
    category: str = Field(default="AI", min_length=1, max_length=100)

    @field_validator("published_date")
    @classmethod
    def published_date_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("publishedDate must include a timezone")
        return value


class NewsFreshness(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    age_hours: float = Field(alias="ageHours", ge=0, le=24)
    date_source: DateSource = Field(alias="dateSource")
    date_confidence: float = Field(alias="dateConfidence", ge=0, le=1)
    is_fresh: Literal[True] = Field(alias="isFresh")


class NewsRecord(CanonicalRecord):
    record_type: Literal["NEWS"] = Field(alias="recordType")
    content: NewsContent
    freshness: NewsFreshness
