"""Asynchronous browser acquisition using Playwright for JavaScript and protected sources."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.fetch.http_client import RawResponse

logger = logging.getLogger(__name__)


class BrowserUnavailableError(RuntimeError):
    """Raised when Playwright is not installed or browser binaries are missing."""


@dataclass(frozen=True, slots=True)
class BrowserSettings:
    headless: bool = True
    timeout_seconds: float = 30.0
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
    viewport_width: int = 1920
    viewport_height: int = 1080
    bypass_csp: bool = True


class AsyncBrowserClient:
    """Async Playwright browser client for JavaScript-rendered or anti-bot protected pages."""

    def __init__(self, settings: BrowserSettings | None = None) -> None:
        self._settings = settings or BrowserSettings()
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._context: Any | None = None

    @classmethod
    def is_available(cls) -> bool:
        """Check whether Playwright is importable in the current environment."""
        try:
            import playwright.async_api
            return True
        except ImportError:
            return False

    async def open(self) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise BrowserUnavailableError(
                "Playwright is not installed. Install with: pip install playwright && playwright install chromium"
            ) from exc

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._settings.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        self._context = await self._browser.new_context(
            user_agent=self._settings.user_agent,
            viewport={
                "width": self._settings.viewport_width,
                "height": self._settings.viewport_height,
            },
            bypass_csp=self._settings.bypass_csp,
            locale="en-US",
            timezone_id="America/New_York",
        )

        # Anti-detection stealth script injection
        await self._context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            """
        )

    async def close(self) -> None:
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def __aenter__(self) -> "AsyncBrowserClient":
        await self.open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def fetch(
        self,
        url: str,
        *,
        wait_selector: str | None = None,
        wait_until: str = "domcontentloaded",
    ) -> RawResponse:
        """Navigate to a URL using Chromium and return a normalized RawResponse."""
        if not self._context:
            await self.open()

        page = await self._context.new_page()
        try:
            # Block unneeded heavy resources for faster scraping
            async def _route_handler(route: Any) -> None:
                if route.request.resource_type in {"image", "media", "font"}:
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", _route_handler)

            response = await page.goto(
                url,
                timeout=int(self._settings.timeout_seconds * 1000),
                wait_until=wait_until,
            )

            if wait_selector:
                await page.wait_for_selector(wait_selector, timeout=10000)

            html_content = await page.content()
            status_code = response.status if response else 200
            headers = dict(response.headers) if response else {}

            return RawResponse(
                url=page.url,
                status_code=status_code,
                headers=headers,
                body=html_content.encode("utf-8"),
            )
        finally:
            await page.close()
