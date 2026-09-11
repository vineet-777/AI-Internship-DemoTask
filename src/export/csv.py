"""Deterministic CSV fallback for the six export tabs."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.export.sheets import REQUIRED_TABS, tabularize


class CsvExporter:
    def __init__(self, output_dir: Path | str) -> None:
        self._output_dir = Path(output_dir)

    def export(self, tabs: Mapping[str, Sequence[object]]) -> dict[str, Path]:
        unknown = set(tabs) - set(REQUIRED_TABS)
        if unknown:
            raise ValueError(f"Unknown export tabs: {sorted(unknown)}")
        self._output_dir.mkdir(parents=True, exist_ok=True)
        outputs: dict[str, Path] = {}
        for tab in REQUIRED_TABS:
            rows = tabularize(tabs.get(tab, []))
            destination = self._output_dir / f"{_filename(tab)}.csv"
            headers = _headers(rows)
            with destination.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
            outputs[tab] = destination
        return outputs


def _headers(rows: list[dict[str, str]]) -> list[str]:
    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    return headers or ["record"]


def _filename(tab: str) -> str:
    return tab.casefold().replace(" ", "_")
