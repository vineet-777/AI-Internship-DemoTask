"""Validated canonical schema for startup records."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from src.schemas.common import CanonicalRecord


class StartupData(BaseModel):
    """Source-supported startup attributes carried by the canonical record."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    description: str | None = Field(default=None, max_length=100_000)
    headquarters: str | None = Field(default=None, max_length=500)
    website: AnyHttpUrl | None = None
    founded_year: int | None = Field(default=None, alias="foundedYear", ge=1800, le=2100)
    employee_count: int | None = Field(default=None, alias="employeeCount", ge=0)
    funding: str | None = Field(default=None, max_length=500)
    canonical_entity_id: str | None = Field(default=None, alias="canonicalEntityId", min_length=1)
    raw_entity_name: str | None = Field(default=None, alias="rawEntityName", min_length=1)
    resolution_confidence: float | None = Field(
        default=None, alias="resolutionConfidence", ge=0, le=1
    )


class StartupContent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    entity_name: str = Field(alias="entityName", min_length=1, max_length=500)
    data: StartupData


class StartupRecord(CanonicalRecord):
    record_type: Literal["STARTUP"] = Field(alias="recordType")
    content: StartupContent
