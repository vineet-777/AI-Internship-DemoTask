"""Tests for AsyncBrowserClient."""

from __future__ import annotations

import pytest

from src.fetch.browser import AsyncBrowserClient, BrowserSettings


def test_browser_client_settings() -> None:
    settings = BrowserSettings(headless=True, timeout_seconds=15.0)
    client = AsyncBrowserClient(settings)
    assert client._settings.headless is True
    assert client._settings.timeout_seconds == 15.0


def test_browser_is_available() -> None:
    # is_available should return a boolean without throwing an unhandled exception
    available = AsyncBrowserClient.is_available()
    assert isinstance(available, bool)
