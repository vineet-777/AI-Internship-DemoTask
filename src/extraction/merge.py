"""Deterministic merge for structured outputs from semantic chunks."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def merge_extractions(values: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for value in values:
        merged = _merge_value(merged, value)
    return merged


def _merge_value(left: Any, right: Any) -> Any:
    if left is None or left == {} or left == []:
        return deepcopy(right)
    if right is None or right == {} or right == []:
        return deepcopy(left)
    if isinstance(left, dict) and isinstance(right, dict):
        result = deepcopy(left)
        for key, value in right.items():
            result[key] = _merge_value(result[key], value) if key in result else deepcopy(value)
        return result
    if isinstance(left, list) and isinstance(right, list):
        result = deepcopy(left)
        for value in right:
            if value not in result:
                result.append(deepcopy(value))
        return result
    return deepcopy(left)
