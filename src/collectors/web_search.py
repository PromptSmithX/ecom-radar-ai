"""Web Search collector using DuckDuckGo Search (ddgs).

Collects market price guides, best sellers, and competitor benchmarks from the web.
100% Free, no API keys or accounts required.
"""

from __future__ import annotations
import logging
from typing import List
from ddgs import DDGS
from src.core.cache import cache
from src.core.config import settings
from src.core.models import Evidence, Niche
from .base import Collector

logger = logging.getLogger(__name__)


class WebSearchCollector(Collector):
    name: str = "web_search"

    def __init__(self):
        cfg = getattr(settings.collectors, "web_search", None)
        self.max_results: int = getattr(cfg, "max_results", 5) if cfg else 5

    def collect(self, niche: Niche, use_cache: bool = True) -> List[Evidence]:
        if use_cache:
            cached_data = cache.get_raw(self.name, niche.name)
            if cached_data is not None:
                return [Evidence(**item) for item in cached_data]

        evidence_list: List[Evidence] = []
        raw_results = []
        query = f"{niche.name} best sellers price guide market 2026"

        try:
            results = list(DDGS(timeout=10).text(query, max_results=self.max_results))
            for r in results:
                title = r.get("title", "")
                url = r.get("href", "")
                body = r.get("body", "")
                if not url:
                    continue

                is_price = any(w in body.lower() or w in title.lower() for w in ["$", "price", "cost", "giá", "under $"])
                ev = Evidence(
                    source=self.name,
                    kind="price" if is_price else "competitor",
                    keyword=niche.name,
                    text=f"{title}: {body[:250]}",
                    value="Khảo sát thị trường web",
                    source_url=url,
                    title=title,
                    snippet=body[:300],
                )
                evidence_list.append(ev)
                raw_results.append(ev.model_dump())
        except Exception as e:
            logger.warning(f"DuckDuckGo web search failed for '{niche.name}': {e}.")

        if raw_results:
            cache.set_raw(self.name, niche.name, raw_results)

        logger.info(f"WebSearchCollector collected {len(evidence_list)} items for '{niche.name}'.")
        return evidence_list
