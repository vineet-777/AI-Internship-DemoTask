"""Playwright-based browser fallback for JavaScript-rendered and anti-bot-protected pages."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from src.fetch.http_client import RawResponse

logger = logging.getLogger(__name__)

# Status codes and content-length thresholds that trigger the browser fallback
ANTIBOT_STATUS_CODES = {403, 503}
MIN_USEFUL_CONTENT_LENGTH = 150

# Known anti-bot challenge markers in response bodies
CHALLENGE_MARKERS = (
    b"cf-browser-verification",
    b"challenge-platform",
    b"Just a moment",
    b"Checking your browser",
    b"DDoS protection by",
    b"Attention Required",
    b"datadome",
)


def should_use_browser_fallback(
    status_code: int,
    body: bytes,
) -> bool:
    """Decide whether to retry the request via a headless browser."""
    if status_code in ANTIBOT_STATUS_CODES:
        return True
    if len(body) < MIN_USEFUL_CONTENT_LENGTH:
        return True
    body_lower = body[:4096].lower()
    return any(marker.lower() in body_lower for marker in CHALLENGE_MARKERS)


async def fetch_with_playwright(
    url: str,
    *,
    timeout_ms: int = 30_000,
    wait_until: str = "networkidle",
) -> RawResponse:
    """Fetch a page using a headless Chromium browser via Playwright.

    Launches a fresh browser context per call to avoid cookie/session leakage
    between sources. The browser is closed after the page content is captured.

    Returns a ``RawResponse`` compatible with the existing pipeline so
    callers can transparently substitute it for the HTTP client result.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright is required for browser-based fetching. "
            "Install it with: pip install playwright && playwright install chromium"
        ) from exc

    logger.info("playwright_fetch_start url=%s", url)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                java_script_enabled=True,
            )
            page = await context.new_page()
            response = await page.goto(url, wait_until=wait_until, timeout=timeout_ms)

            # Some anti-bot pages need extra time after initial load
            try:
                await page.wait_for_load_state("networkidle", timeout=5_000)
            except Exception:
                pass

            content = await page.content()
            body = content.encode("utf-8")
            status_code = response.status if response else 200
            headers = dict(response.headers) if response else {}

            logger.info(
                "playwright_fetch_complete url=%s status=%d bytes=%d",
                url,
                status_code,
                len(body),
            )

            return RawResponse(
                request_url=url,
                response_url=page.url,
                status_code=status_code,
                headers=headers,
                body=body,
                retrieved_at=datetime.now(UTC),
                attempts=1,
            )
        finally:
            await browser.close()
