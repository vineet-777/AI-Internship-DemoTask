"""Validated canonical schema for product records."""

from __future__ import annotations

from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from src.schemas.common import CanonicalRecord

PricingModel = Literal["FREE", "FREEMIUM", "PAID", "ENTERPRISE"]


class ProductContent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    product_name: str | None = Field(default=None, alias="productName", max_length=500)
    startup_name: str = Field(alias="startupName", min_length=1, max_length=500)
    pricing_model: PricingModel = Field(alias="pricingModel")
    description: str | None = Field(default=None, max_length=100_000)
    website: AnyHttpUrl | None = None
    canonical_entity_id: str | None = Field(default=None, alias="canonicalEntityId", min_length=1)
    raw_startup_name: str | None = Field(default=None, alias="rawStartupName", min_length=1)
    resolution_confidence: float | None = Field(
        default=None, alias="resolutionConfidence", ge=0, le=1
    )


class ProductRecord(CanonicalRecord):
    record_type: Literal["PRODUCT"] = Field(alias="recordType")
    content: ProductContent
