"""Amazon search-results collector.

Scrapes amazon.com/s?k=<seed> for product cards (title, price, rating, review
count, Best Seller/Amazon's Choice badge). No API key required, but the host IP
can be blocked (503/CAPTCHA), so this uses the same circuit-breaker pattern as
GoogleTrendsCollector: a 429/503/CAPTCHA response sets a cooldown and subsequent
calls are skipped until it expires. On failure this returns [] — it never
fabricates product data, to preserve the project's anti-hallucination guarantee.
"""

from __future__ import annotations
import logging
import re
import time
import urllib.parse
from datetime import datetime, timedelta
from typing import Callable, List, Optional
import httpx
from bs4 import BeautifulSoup
from src.core.cache import cache
from src.core.config import settings
from src.core.models import Evidence, Niche
from .base import Collector

logger = logging.getLogger(__name__)

COOLDOWN_META_KEY = "amazon_cooldown"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

CAPTCHA_MARKERS = (
    "captcha",
    "robot check",
    "api-services-support@amazon.com",
    "bm-verify",  # Akamai Bot Manager challenge/redirect page served with HTTP 200
)


class AmazonCollector(Collector):
    name: str = "amazon"

    def __init__(self, client_factory: Optional[Callable[[], httpx.Client]] = None):
        cfg = settings.collectors.amazon
        self.enabled = cfg.enabled
        self.max_results = cfg.max_results
        self.sleep_seconds = cfg.sleep_seconds
        self.cooldown_minutes = cfg.cooldown_minutes
        self.region_domain = cfg.region_domain
        self._client_factory = client_factory or (
            lambda: httpx.Client(timeout=15.0, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
        )

    def _search_url(self, seed: str) -> str:
        return f"https://{self.region_domain}/s?k={urllib.parse.quote_plus(seed)}"

    def _is_blocked(self, status_code: int, body: str) -> bool:
        if status_code in (429, 503):
            return True
        lowered = body.lower()
        return any(marker in lowered for marker in CAPTCHA_MARKERS)

    def _parse_price(self, card) -> Optional[str]:
        price_el = card.select_one(".a-price .a-offscreen")
        if price_el and price_el.text.strip():
            return price_el.text.strip()
        return None

    def _parse_rating(self, card) -> Optional[str]:
        rating_el = card.select_one(".a-icon-alt")
        if rating_el and rating_el.text.strip():
            match = re.search(r"[\d.]+", rating_el.text)
            return match.group(0) if match else None
        return None

    def _parse_review_count(self, card) -> Optional[str]:
        for el in card.select("span.a-size-base, span[aria-label]"):
            text = el.get("aria-label") or el.text
            if text and re.fullmatch(r"[\d,]+", text.strip()):
                return text.strip()
        return None

    def _has_badge(self, card) -> bool:
        badge_text = card.get_text(" ", strip=True).lower()
        return "best seller" in badge_text or "amazon's choice" in badge_text

    def _parse_cards(self, html: str, seed: str) -> List[Evidence]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select('div[data-component-type="s-search-result"]')
        evidence_list: List[Evidence] = []

        for card in cards[: self.max_results]:
            # Amazon's markup has shifted the product link out of <h2> into a sibling
            # <a>; matching on href containing "/dp/" (the product detail path) is
            # resilient to further layout churn than a fixed "h2 a" selector.
            link_el = card.select_one('a[href*="/dp/"]')
            title_el = card.select_one("h2 span") or (link_el.select_one("span") if link_el else None)
            if link_el is None or not link_el.get("href") or title_el is None:
                continue

            title = title_el.text.strip()
            if not title:
                continue

            href = link_el["href"]
            product_url = href if href.startswith("http") else f"https://{self.region_domain}{href}"

            price = self._parse_price(card)
            rating = self._parse_rating(card)
            review_count = self._parse_review_count(card)
            has_badge = self._has_badge(card)

            parts = [title]
            if price:
                parts.append(price)
            if rating and review_count:
                parts.append(f"{rating}★, {review_count} reviews")
            elif rating:
                parts.append(f"{rating}★")
            if has_badge:
                parts.append("[Best Seller/Amazon's Choice]")
            text = " — ".join(parts)

            ev = Evidence(
                source=self.name,
                kind="price" if price else "competitor",
                keyword=seed,
                text=text,
                value=price,
                title=title,
                source_url=product_url,
            )
            evidence_list.append(ev)

        return evidence_list

    def collect(self, niche: Niche, use_cache: bool = True) -> List[Evidence]:
        # 1. Cache first
        if use_cache:
            cached_data = cache.get_raw(self.name, niche.name)
            if cached_data is not None:
                logger.info(f"Loaded Amazon data from cache for niche: {niche.name}")
                return [Evidence(**item) for item in cached_data]

        # 2. Feature flag off: return empty without touching the network
        if not self.enabled:
            logger.info(f"AmazonCollector disabled by config; skipping '{niche.name}'.")
            return []

        # 3. Circuit breaker: skip real calls while a previous block is on cooldown
        cooldown_meta = cache.get_meta(COOLDOWN_META_KEY)
        if cooldown_meta and cooldown_meta.get("limited_until"):
            try:
                limited_until = datetime.fromisoformat(cooldown_meta["limited_until"])
                if datetime.now() < limited_until:
                    logger.warning(
                        f"Amazon đang trong cooldown do bị chặn trước đó (hết lúc {limited_until.isoformat()}). "
                        f"Bỏ qua gọi thật cho '{niche.name}'."
                    )
                    return []
            except (ValueError, TypeError):
                pass

        kw_list = niche.seed_keywords if niche.seed_keywords else [niche.name]
        evidence_list: List[Evidence] = []
        raw_results = []
        blocked = False

        try:
            client = self._client_factory()
        except Exception as e:
            logger.warning(f"Could not initialize Amazon HTTP client: {e}")
            return []

        with client:
            for kw in kw_list:
                if blocked:
                    break
                try:
                    resp = client.get(self._search_url(kw))
                except Exception as e:
                    logger.warning(f"Amazon search for '{kw}' failed: {e}")
                    continue

                if self._is_blocked(resp.status_code, resp.text):
                    logger.warning("Amazon returned a block/CAPTCHA response. Setting cooldown and stopping.")
                    blocked = True
                    limited_until = datetime.now() + timedelta(minutes=self.cooldown_minutes)
                    cache.set_meta(COOLDOWN_META_KEY, {"limited_until": limited_until.isoformat()})
                    break

                if resp.status_code != 200:
                    logger.warning(f"Amazon search for '{kw}' returned status {resp.status_code}.")
                    continue

                items = self._parse_cards(resp.text, kw)
                evidence_list.extend(items)
                raw_results.extend(ev.model_dump() for ev in items)

                time.sleep(self.sleep_seconds)

        if raw_results:
            cache.set_raw(self.name, niche.name, raw_results)

        return evidence_list
