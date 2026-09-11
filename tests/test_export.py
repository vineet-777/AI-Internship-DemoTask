from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from scripts.generate_architecture_pdf import generate_pdf
from src.export.csv import CsvExporter
from src.export.sheets import REQUIRED_TABS, GoogleSheetsExporter, tabularize


def test_tabularize_serializes_nested_records() -> None:
    rows = tabularize([{"recordId": "one", "content": {"title": "AI"}}])
    assert rows == [{"recordId": "one", "content": '{"title": "AI"}'}]


def test_csv_export_writes_all_six_tabs(tmp_path: Path) -> None:
    outputs = CsvExporter(tmp_path).export({"News": [{"title": "Fresh"}]})
    assert set(outputs) == set(REQUIRED_TABS)
    assert (tmp_path / "news.csv").read_text(encoding="utf-8").startswith("title\nFresh")
    assert (tmp_path / "startups.csv").exists()


def test_csv_export_rejects_unknown_tabs(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        CsvExporter(tmp_path).export({"Unknown": []})


def test_architecture_pdf_has_three_pages(tmp_path: Path) -> None:
    output = generate_pdf(tmp_path / "architecture.pdf")
    content = output.read_bytes()
    assert content.startswith(b"%PDF-1.4")
    assert content.count(b"/Type /Page ") == 3


async def test_google_sheets_export_batches_tab_creation_and_values() -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, str(request.url)))
        if request.method == "GET":
            return httpx.Response(200, json={"sheets": []}, request=request)
        return httpx.Response(200, json={}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        exporter = GoogleSheetsExporter("sheet-1", "token", client=client, api_base_url="https://sheets.test")
        await exporter.export({"News": [{"title": "Fresh"}]})

    assert len(requests) == 4
    assert requests[0][0] == "GET"
    assert requests[1][1].endswith(":batchUpdate")
    assert requests[2][1].endswith("/values:batchClear")
    assert requests[3][1].endswith("/values:batchUpdate")
