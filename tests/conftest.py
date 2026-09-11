from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def arxiv_xml() -> bytes:
    return (Path(__file__).parent / "fixtures" / "arxiv_single_entry.xml").read_bytes()
