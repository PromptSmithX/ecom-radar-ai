"""Playwright Stealth Browser Manager for headless web scraping.

Provides a singleton / managed Playwright context with realistic browser
fingerprints to safely scrape Reddit, Amazon, and e-commerce platforms
without triggering anti-bot or CAPTCHA blocks.
"""

from __future__ import annotations
import atexit
import logging
import random
import time
from pathlib import Path
from typing import Optional
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright
from src.core.config import BASE_DIR, settings

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
"""


class BrowserManager:
    """Manages a persistent, stealth Playwright Chromium instance."""

    _instance: Optional[BrowserManager] = None
    _playwright: Optional[Playwright] = None
    _browser: Optional[Browser] = None
    _context: Optional[BrowserContext] = None

    def __init__(self):
        self.profile_dir = BASE_DIR / "data" / ".browser_profile"
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.headless = True
        self.timeout_ms = 25000

    @classmethod
    def get_instance(cls) -> BrowserManager:
        if cls._instance is None:
            cls._instance = cls()
            atexit.register(cls.close_all)
        return cls._instance

    def _ensure_browser(self):
        if self._playwright is None:
            self._playwright = sync_playwright().start()

        if self._browser is None:
            logger.info("Launching Playwright Chromium browser...")
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-infobars",
                ],
            )

        if self._context is None:
            self._context = self._browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1366, "height": 768},
                locale="en-US",
                timezone_id="America/New_York",
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            # Normalize currency to USD for Amazon US scraping
            try:
                self._context.add_cookies([
                    {"name": "i18n-prefs", "value": "USD", "domain": ".amazon.com", "path": "/"},
                    {"name": "lc-main", "value": "en_US", "domain": ".amazon.com", "path": "/"},
                ])
            except Exception as e:
                logger.debug(f"Could not preset Amazon cookies: {e}")

            self._context.add_init_script(STEALTH_INIT_SCRIPT)
            self._context.set_default_timeout(self.timeout_ms)

    def new_page(self) -> Page:
        """Returns a new stealth page from the active context."""
        self._ensure_browser()
        assert self._context is not None
        return self._context.new_page()

    def fetch_page_content(
        self,
        url: str,
        wait_selector: Optional[str] = None,
        delay_seconds: float = 2.0,
        timeout_ms: Optional[int] = None,
    ) -> str:
        """Navigates to URL, waits for selector/delay, and returns page HTML."""
        self._ensure_browser()
        page = self.new_page()
        try:
            effective_timeout = timeout_ms or self.timeout_ms
            logger.info(f"Browser navigating to: {url} (timeout={effective_timeout}ms)")
            page.goto(url, timeout=effective_timeout, wait_until="domcontentloaded")
            
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=5000)
                except Exception:
                    logger.debug(f"Selector '{wait_selector}' not found within timeout on {url}")

            if delay_seconds > 0:
                jitter = random.uniform(0.5, 1.5)
                time.sleep(delay_seconds + jitter)

            return page.content()
        finally:
            try:
                page.close()
            except Exception:
                pass

    @classmethod
    def close_all(cls):
        """Closes browser context and playwright instance gracefully."""
        if cls._instance is not None:
            inst = cls._instance
            try:
                if inst._context is not None:
                    inst._context.close()
                    inst._context = None
            except Exception as e:
                logger.debug(f"Error closing browser context: {e}")

            try:
                if inst._browser is not None:
                    inst._browser.close()
                    inst._browser = None
            except Exception as e:
                logger.debug(f"Error closing browser: {e}")

            try:
                if inst._playwright is not None:
                    inst._playwright.stop()
                    inst._playwright = None
            except Exception as e:
                logger.debug(f"Error stopping playwright: {e}")

            cls._instance = None
            logger.info("Playwright browser instance closed cleanly.")


browser_manager = BrowserManager.get_instance()
