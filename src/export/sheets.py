"""Batch Google Sheets exporter with a deterministic tab contract."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import httpx
from pydantic import BaseModel

REQUIRED_TABS = (
    "Startups",
    "Products",
    "Research Papers",
    "Jobs",
    "News",
    "Entity Mapping Log",
)

POSTGRES_TABLES = {
    "Startups": "startups",
    "Products": "products",
    "Research Papers": "research_papers",
    "Jobs": "jobs",
    "News": "news",
    "Entity Mapping Log": "entity_mapping_log",
}


class PostgresExportSource:
    """Read validated JSON payloads from the six fixed export tables."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    async def read_tabs(self) -> dict[str, list[object]]:
        tabs: dict[str, list[object]] = {}
        for tab, table in POSTGRES_TABLES.items():
            rows = await self._connection.fetch(
                f"SELECT record_payload FROM {table} ORDER BY record_id"
            )
            tabs[tab] = [
                row["record_payload"] if isinstance(row, Mapping) else row[0]
                for row in rows
            ]
        return tabs


class GoogleSheetsExporter:
    """Export six validated tab datasets through the Sheets REST API."""

    def __init__(
        self,
        spreadsheet_id: str,
        access_token: str,
        *,
        client: httpx.AsyncClient | None = None,
        api_base_url: str = "https://sheets.googleapis.com/v4/spreadsheets",
    ) -> None:
        if not spreadsheet_id or not access_token:
            raise ValueError("spreadsheet_id and access_token are required")
        self._spreadsheet_id = spreadsheet_id
        self._headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        self._base_url = api_base_url.rstrip("/")
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> "GoogleSheetsExporter":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30)
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def export(self, tabs: Mapping[str, Sequence[object]]) -> None:
        _validate_tabs(tabs)
        client, owns_client = self._request_client()
        try:
            spreadsheet = await client.get(
                f"{self._base_url}/{self._spreadsheet_id}",
                headers=self._headers,
                params={"fields": "sheets.properties.title"},
            )
            spreadsheet.raise_for_status()
            existing = {
                sheet["properties"]["title"]
                for sheet in spreadsheet.json().get("sheets", [])
                if isinstance(sheet, dict) and isinstance(sheet.get("properties"), dict)
            }
            missing = [tab for tab in REQUIRED_TABS if tab not in existing]
            if missing:
                response = await client.post(
                    f"{self._base_url}/{self._spreadsheet_id}:batchUpdate",
                    headers=self._headers,
                    json={"requests": [{"addSheet": {"properties": {"title": tab}}} for tab in missing]},
                )
                response.raise_for_status()
            ranges = [f"'{tab}'" for tab in REQUIRED_TABS]
            clear = await client.post(
                f"{self._base_url}/{self._spreadsheet_id}/values:batchClear",
                headers=self._headers,
                json={"ranges": ranges},
            )
            clear.raise_for_status()
            data = []
            for tab in REQUIRED_TABS:
                rows = tabularize(tabs.get(tab, []))
                data.append(
                    {
                        "range": f"'{tab}'!A1",
                        "majorDimension": "ROWS",
                        "values": _matrix(rows),
                    }
                )
            update = await client.post(
                f"{self._base_url}/{self._spreadsheet_id}/values:batchUpdate",
                headers=self._headers,
                json={"valueInputOption": "RAW", "data": data},
            )
            update.raise_for_status()
        finally:
            if owns_client:
                await client.aclose()

    def _request_client(self) -> tuple[httpx.AsyncClient, bool]:
        if self._client is not None:
            return self._client, False
        return httpx.AsyncClient(timeout=30), True


def tabularize(records: Sequence[object]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for record in records:
        value = record.model_dump(mode="json", by_alias=True) if isinstance(record, BaseModel) else record
        if not isinstance(value, Mapping):
            raise TypeError("Export records must be mappings or Pydantic models")
        rows.append({str(key): _cell(value) for key, value in value.items()})
    return rows


def _validate_tabs(tabs: Mapping[str, Sequence[object]]) -> None:
    unknown = set(tabs) - set(REQUIRED_TABS)
    if unknown:
        raise ValueError(f"Unknown export tabs: {sorted(unknown)}")


def _matrix(rows: list[dict[str, str]]) -> list[list[str]]:
    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    if not headers:
        return [["record"]]
    return [headers] + [[row.get(header, "") for header in headers] for row in rows]


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return str(value)
