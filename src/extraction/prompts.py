"""Structured extraction prompt construction."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


SYSTEM_INSTRUCTIONS = """Extract only facts explicitly supported by the supplied source text.
Return only one JSON object matching the requested schema.
Use null or empty values when evidence is absent. Do not guess, invent URLs, or infer missing facts.
"""


def build_extraction_prompt(
    text: str,
    schema: type[BaseModel],
    *,
    source_context: str | None = None,
) -> str:
    schema_json = json.dumps(schema.model_json_schema(), indent=2, sort_keys=True)
    context = f"Source context: {source_context}\n\n" if source_context else ""
    return (
        f"{SYSTEM_INSTRUCTIONS}\n{context}"
        f"JSON schema:\n{schema_json}\n\n"
        f"Source text:\n{text}"
    )
