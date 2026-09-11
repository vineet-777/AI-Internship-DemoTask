"""Canonical schema for fresh job records."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.schemas.common import CanonicalRecord


class JobContent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    company: str = Field(min_length=1, max_length=500)
    date: datetime
    is_remote: bool = Field(alias="isRemote")
    role_family: str | None = Field(default=None, alias="roleFamily", max_length=200)
    title: str = Field(min_length=1, max_length=2_000)
    description: str = Field(min_length=1, max_length=200_000)

    @field_validator("date")
    @classmethod
    def date_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("date must include a timezone")
        return value


class JobRecord(CanonicalRecord):
    record_type: Literal["JOB"] = Field(alias="recordType")
    content: JobContent
