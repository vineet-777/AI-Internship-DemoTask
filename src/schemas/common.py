"""Provenance-bearing common fields for canonical records."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class SourceReference(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    url: AnyHttpUrl
    canonical_url: AnyHttpUrl = Field(alias="canonicalUrl")


class Provenance(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    retrieved_at: datetime = Field(alias="retrievedAt")
    content_hash: str = Field(alias="contentHash")
    raw_document_id: str = Field(alias="rawDocumentId", min_length=1)
    extraction_method: Literal["deterministic"] = Field(alias="extractionMethod")
    extraction_metadata: dict[str, Any] = Field(alias="extractionMetadata")
    validation_status: Literal["VALID"] = Field(alias="validationStatus")

    @field_validator("retrieved_at")
    @classmethod
    def timestamp_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrievedAt must include a timezone")
        return value

    @field_validator("content_hash")
    @classmethod
    def content_hash_must_be_sha256(cls, value: str) -> str:
        if not SHA256_RE.fullmatch(value):
            raise ValueError("contentHash must be a lowercase SHA-256 hex digest")
        return value


class CanonicalRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    record_id: str = Field(alias="recordId", min_length=1)
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    source: SourceReference
    collected_at: datetime = Field(alias="collectedAt")
    provenance: Provenance

    @field_validator("collected_at")
    @classmethod
    def collection_timestamp_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("collectedAt must include a timezone")
        return value
