"""Post-provider JSON and Pydantic validation."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError


class ExtractionValidationError(ValueError):
    """Provider output failed JSON or schema validation."""


def validate_extraction(value: dict[str, Any] | str, schema: type[BaseModel]) -> BaseModel:
    try:
        payload: Any = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError as exc:
        raise ExtractionValidationError("LLM output is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ExtractionValidationError("LLM output must be a JSON object")
    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        raise ExtractionValidationError(str(exc)) from exc
