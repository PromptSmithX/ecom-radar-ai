"""Web Search collector using Tavily API."""

from __future__ import annotations
import logging
from typing import List
from src.core.cache import cache
from src.core.config import settings
from src.core.models import Evidence, Niche
from .base import Collector

logger = logging.getLogger(__name__)


class WebSearchCollector(Collector):
    name: str = "web_search"

    def __init__(self):
        self.max_results = settings.collectors.web_search.max_results
        self.api_key = settings.tavily_api_key

    def collect(self, niche: Niche, use_cache: bool = True) -> List[Evidence]:
        evidence_list: List[Evidence] = []

        # 1. Check cache first if enabled
        if use_cache:
            cached_data = cache.get_raw(self.name, niche.name)
            if cached_data is not None:
                return [Evidence(**item) for item in cached_data]

        raw_results = []

        # 2. Try Tavily API if key is present
        if not self.api_key or not self.api_key.strip():
            logger.warning(f"Tavily API key missing — no web search data collected for '{niche.name}'.")
            return []

        try:
            from tavily import TavilyClient
            tavily_client = TavilyClient(api_key=self.api_key)
            query = f"{niche.name} best sellers price guide competition 2026"
            response = tavily_client.search(query=query, max_results=self.max_results)
            results = response.get("results", [])
            for r in results:
                title = r.get("title", "")
                url = r.get("url", "")
                content = r.get("content", "")
                if not url:
                    continue
                ev = Evidence(
                    source=self.name,
                    kind="price" if any(w in content.lower() for w in ["$", "price", "cost", "giá"]) else "competitor",
                    keyword=niche.name,
                    text=f"{title}: {content[:200]}...",
                    value="Web Search Result",
                    source_url=url,
                )
                evidence_list.append(ev)
                raw_results.append(ev.model_dump())
        except Exception as e:
            logger.warning(f"Tavily search failed for '{niche.name}': {e}. No web search data collected.")

        if raw_results:
            cache.set_raw(self.name, niche.name, raw_results)

        return evidence_list
