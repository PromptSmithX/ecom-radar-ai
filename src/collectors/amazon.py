"""Amazon product and keyword collector using Playwright Stealth and Completion API.

Collects authentic product prices, ratings, review counts, and Best Seller badges
from amazon.com search results, plus buyer search keyword suggestions via Amazon's
public completion API. 100% Free, no API keys or proxies required.
"""

from __future__ import annotations
import logging
import re
import urllib.parse
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
import httpx
from bs4 import BeautifulSoup
from src.core.browser import BrowserManager
from src.core.cache import cache
from src.core.config import settings
from src.core.models import Evidence, Niche
from .base import Collector

logger = logging.getLogger(__name__)

AMAZON_SUGGEST_URL = "https://completion.amazon.com/api/2017/suggestions"
COOLDOWN_META_KEY = "amazon_cooldown"
CAPTCHA_MARKERS = ("captcha", "robot check", "api-services-support@amazon.com", "bm-verify")


class AmazonCollector(Collector):
    name: str = "amazon"

    def __init__(
        self,
        browser_manager: Optional[BrowserManager] = None,
        client_factory: Optional[Callable[[], httpx.Client]] = None,
    ):
        cfg = getattr(settings.collectors, "amazon", None)
        self.enabled = getattr(cfg, "enabled", True) if cfg else True
        self.max_results = getattr(cfg, "max_results", 8) if cfg else 8
        self.sleep_seconds = getattr(cfg, "sleep_seconds", 1.5) if cfg else 1.5
        self.cooldown_minutes = getattr(cfg, "cooldown_minutes", 30) if cfg else 30
        self.region_domain = getattr(cfg, "region_domain", "www.amazon.com") if cfg else "www.amazon.com"
        self.browser_manager = browser_manager or BrowserManager.get_instance()
        self._client_factory = client_factory

    def _fetch_amazon_suggestions(self, seed: str) -> List[Evidence]:
        """Fetches buyer autocomplete queries from Amazon Completion API ($0, no CAPTCHA)."""
        evidence_items: List[Evidence] = []
        try:
            params = {
                "mid": "ATVPDKIKX0DER",  # Amazon US
                "alias": "aps",
                "prefix": seed,
            }
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(AMAZON_SUGGEST_URL, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    suggestions = data.get("suggestions", [])
                    for s in suggestions[:4]:
                        val = s.get("value")
                        if val and val.lower() != seed.lower():
                            encoded = urllib.parse.quote_plus(val)
                            evidence_items.append(
                                Evidence(
                                    source=self.name,
                                    kind="keyword_signal",
                                    keyword=val,
                                    text=f"Từ khóa tìm kiếm mua sắm phổ biến trên Amazon: '{val}'.",
                                    value="Amazon Search Autocomplete",
                                    source_url=f"https://{self.region_domain}/s?k={encoded}",
                                )
                            )
        except Exception as e:
            logger.debug(f"Amazon suggestion fetch error for '{seed}': {e}")
        return evidence_items

    def _parse_html_cards(self, html: str, seed: str) -> List[Evidence]:
        """Parses product cards from HTML content."""
        evidence_items: List[Evidence] = []
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("div", attrs={"data-component-type": "s-search-result"})

        for card in cards[: self.max_results]:
            asin = card.get("data-asin", "").strip()

            # Title & link
            link_el = card.find("a", href=re.compile(r"/dp/"))
            title_el = card.find("h2")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue

            product_url = f"https://{self.region_domain}/dp/{asin}" if asin else (
                f"https://{self.region_domain}{link_el['href']}" if link_el and link_el.get("href", "").startswith("/") else (
                    link_el["href"] if link_el and link_el.get("href", "").startswith("http") else f"https://{self.region_domain}/s?k={urllib.parse.quote_plus(seed)}"
                )
            )

            # Price
            price_el = card.find("span", class_="a-offscreen")
            price_text = price_el.get_text(strip=True) if price_el else None
            if not price_text:
                whole = card.find("span", class_="a-price-whole")
                frac = card.find("span", class_="a-price-fraction")
                if whole:
                    price_text = f"${whole.get_text(strip=True)}.{frac.get_text(strip=True) if frac else '00'}"

            # Rating & reviews count
            rating_el = card.find("span", class_="a-icon-alt")
            rating_text = rating_el.get_text(strip=True) if rating_el else None

            review_el = card.find("span", class_="a-size-base")
            review_count = review_el.get_text(strip=True) if review_el and re.match(r"^[\d,]+$", review_el.get_text(strip=True)) else None

            # Badges
            card_text_lower = card.get_text(" ", strip=True).lower()
            badge = None
            if "best seller" in card_text_lower:
                badge = "Best Seller"
            elif "amazon's choice" in card_text_lower:
                badge = "Amazon's Choice"

            # Build evidence text
            parts = [f"Sản phẩm Amazon: '{title}'"]
            if price_text:
                parts.append(f"Giá: {price_text}")
            if rating_text:
                parts.append(f"Đánh giá: {rating_text}")
            if review_count:
                parts.append(f"({review_count} lượt review)")
            if badge:
                parts.append(f"[{badge}]")

            full_text = " — ".join(parts)

            evidence_items.append(
                Evidence(
                    source=self.name,
                    kind="price" if price_text else "competitor",
                    keyword=seed,
                    text=full_text,
                    value=price_text if price_text else None,
                    source_url=product_url,
                    title=title,
                    rating=rating_text,
                    review_count=review_count,
                    badge=badge,
                )
            )

        return evidence_items

    def _scrape_amazon_search(self, seed: str) -> List[Evidence]:
        """Scrapes product listing cards using client_factory if provided, otherwise BrowserManager."""
        url = f"https://{self.region_domain}/s?k={urllib.parse.quote_plus(seed)}"

        # If a fake client factory is injected (e.g. during unit tests), use it
        if self._client_factory is not None:
            try:
                with self._client_factory() as client:
                    resp = client.get(url)
                    if resp.status_code in (429, 503) or any(m in resp.text.lower() for m in CAPTCHA_MARKERS):
                        limited_until = datetime.now() + timedelta(minutes=self.cooldown_minutes)
                        cache.set_meta(COOLDOWN_META_KEY, {"limited_until": limited_until.isoformat()})
                        return []
                    return self._parse_html_cards(resp.text, seed)
            except Exception as e:
                logger.warning(f"Client factory request failed: {e}")
                return []

        try:
            html = self.browser_manager.fetch_page_content(
                url,
                wait_selector='div[data-component-type="s-search-result"]',
                delay_seconds=2.0,
            )
            return self._parse_html_cards(html, seed)
        except Exception as e:
            logger.warning(f"Error scraping Amazon search for '{seed}': {e}")
            return []

    def collect(self, niche: Niche, use_cache: bool = True) -> List[Evidence]:
        if not self.enabled:
            return []

        # Check cooldown
        cooldown_meta = cache.get_meta(COOLDOWN_META_KEY)
        if cooldown_meta and cooldown_meta.get("limited_until"):
            try:
                limited_until = datetime.fromisoformat(cooldown_meta["limited_until"])
                if datetime.now() < limited_until:
                    logger.warning(f"Amazon is currently in cooldown until {limited_until}. Skipping.")
                    return []
            except Exception:
                pass

        if use_cache:
            cached_data = cache.get_raw(self.name, niche.name)
            if cached_data is not None:
                logger.info(f"Loaded Amazon evidence from cache for niche: {niche.name}")
                return [Evidence(**item) for item in cached_data]

        seeds = niche.seed_keywords if niche.seed_keywords else [niche.name]
        evidence_list: List[Evidence] = []
        seen_urls = set()

        for seed in seeds[:2]:
            # 1. Autocomplete keywords (only in live mode without custom client_factory)
            if self._client_factory is None:
                sug_items = self._fetch_amazon_suggestions(seed)
                for item in sug_items:
                    if item.source_url not in seen_urls:
                        seen_urls.add(item.source_url)
                        evidence_list.append(item)

            # 2. Product search results
            prod_items = self._scrape_amazon_search(seed)
            for item in prod_items:
                if item.source_url not in seen_urls:
                    seen_urls.add(item.source_url)
                    evidence_list.append(item)

        cache.set_raw(self.name, niche.name, [e.model_dump() for e in evidence_list])
        return evidence_list
