"""Etsy marketplace collector.

Collects authentic competitor listings, pricing, and product ideas from Etsy
across all merchant shops using DuckDuckGo search indexing.
Solves the limitation of Etsy API v3 (which only allows accessing one's own shop).
100% Free, no API keys required.
"""

from __future__ import annotations
import logging
import re
from typing import List, Optional, Set
from ddgs import DDGS
from src.core.cache import cache
from src.core.config import settings
from src.core.models import Evidence, Niche
from .base import Collector

logger = logging.getLogger(__name__)

PRICE_REGEX = re.compile(r"(\$\s*\d+(?:\.\d{2})?|\b\d+(?:\.\d{2})?\s*USD\b)", re.IGNORECASE)
ETSY_LISTING_REGEX = re.compile(r"https?://(?:www\.)?etsy\.com/listing/(\d+)(?:/[^\s\"'>]*)?", re.IGNORECASE)


class EtsyCollector(Collector):
    name: str = "etsy"

    def __init__(self):
        cfg = getattr(settings.collectors, "etsy", None)
        self.enabled = getattr(cfg, "enabled", True) if cfg else True
        self.max_results: int = getattr(cfg, "max_results", 8) if cfg else 8

    def _search_etsy_listings(self, seed: str) -> List[Evidence]:
        """Queries DuckDuckGo specifically for Etsy listings matching the seed keyword."""
        evidence_items: List[Evidence] = []
        query = f'site:etsy.com/listing "{seed}"'

        try:
            results = list(DDGS(timeout=10).text(query, max_results=self.max_results))
            for item in results:
                href = item.get("href", "")
                m = ETSY_LISTING_REGEX.search(href)
                if not m:
                    continue

                listing_id = m.group(1)
                canonical_url = f"https://www.etsy.com/listing/{listing_id}"
                title = item.get("title", "").replace(" - Etsy", "").strip()
                body = item.get("body", "").strip()

                # Extract price if present in snippet
                price_match = PRICE_REGEX.search(body)
                price_val = price_match.group(0) if price_match else None

                evidence_text = f"Sản phẩm thủ công/cá nhân hóa trên Etsy: '{title}'."
                if price_val:
                    evidence_text += f" Giá tham khảo: {price_val}."
                if body:
                    evidence_text += f" Mô tả: {body[:250]}"

                val_summary = f"{price_val} (Etsy Listing)" if price_val else "Etsy Handmade/Custom Gift"

                evidence_items.append(
                    Evidence(
                        source=self.name,
                        kind="price" if price_val else "competitor",
                        keyword=seed,
                        text=evidence_text,
                        value=val_summary,
                        source_url=canonical_url,
                        title=title,
                        snippet=body[:300] if body else None,
                    )
                )

        except Exception as e:
            logger.warning(f"Error searching Etsy listings for '{seed}': {e}")

        return evidence_items

    def collect(self, niche: Niche, use_cache: bool = True) -> List[Evidence]:
        if use_cache:
            cached_data = cache.get_raw(self.name, niche.name)
            if cached_data is not None:
                logger.info(f"Loaded Etsy evidence from cache for niche: {niche.name}")
                return [Evidence(**item) for item in cached_data]

        seeds = niche.seed_keywords if niche.seed_keywords else [niche.name]
        evidence_list: List[Evidence] = []
        seen_urls: Set[str] = set()

        for seed in seeds[:2]:
            items = self._search_etsy_listings(seed)
            for item in items:
                if item.source_url not in seen_urls:
                    seen_urls.add(item.source_url)
                    evidence_list.append(item)
                if len(evidence_list) >= self.max_results:
                    break
            if len(evidence_list) >= self.max_results:
                break

        cache.set_raw(self.name, niche.name, [e.model_dump() for e in evidence_list])
        logger.info(f"EtsyCollector collected {len(evidence_list)} authentic listings for '{niche.name}'.")
        return evidence_list
