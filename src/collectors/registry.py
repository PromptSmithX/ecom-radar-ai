"""Collector registry and orchestrator."""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Type
from src.core.config import settings
from src.core.models import Evidence, Niche
from .amazon import AmazonCollector
from .base import Collector
from .etsy import EtsyCollector
from .google_suggest import GoogleSuggestCollector
from .google_trends import GoogleTrendsCollector
from .reddit import RedditCollector
from .serpapi_trends import SerpApiTrendsCollector
from .web_search import WebSearchCollector

logger = logging.getLogger(__name__)

COLLECTORS: List[Type[Collector]] = [
    GoogleSuggestCollector,
    GoogleTrendsCollector,
    RedditCollector,
    WebSearchCollector,
    AmazonCollector,
    EtsyCollector,
]

# Interchangeable trend-data providers: GoogleTrendsCollector vs SerpApiTrendsCollector
TREND_PROVIDERS: Dict[str, Type[Collector]] = {
    "google_trends": GoogleTrendsCollector,
    "serpapi": SerpApiTrendsCollector,
}


def build_collectors(
    trend_provider: Optional[str] = None,
    trend_api_key: Optional[str] = None,
    use_amazon: Optional[bool] = None,
    use_etsy: Optional[bool] = None,
) -> List[Collector]:
    """Instantiates the canonical collector list.
    All collectors (Reddit, Amazon, Etsy, WebSearch, Suggest) run 100% free without Tavily.
    """
    trend_provider = trend_provider or settings.collectors.trend_provider
    trend_cls = TREND_PROVIDERS.get(trend_provider, GoogleTrendsCollector)
    use_amazon = settings.collectors.amazon.enabled if use_amazon is None else use_amazon
    use_etsy = settings.collectors.etsy.enabled if use_etsy is None else use_etsy

    instances: List[Collector] = []
    for cls in COLLECTORS:
        if cls in TREND_PROVIDERS.values():
            instances.append(trend_cls(api_key=trend_api_key) if trend_provider == "serpapi" else trend_cls())
        elif cls is AmazonCollector:
            if use_amazon:
                instances.append(cls())
        elif cls is EtsyCollector:
            if use_etsy:
                instances.append(cls())
        else:
            instances.append(cls())
    return instances


def collect_for_niche(niche: Niche, collectors: Optional[List[Collector]] = None, use_cache: bool = True) -> List[Evidence]:
    """Runs all registered collectors for a given niche.
    Gracefully handles failures per collector so the rest still run.
    """
    if collectors is None:
        collectors = build_collectors()

    all_evidence: List[Evidence] = []

    for collector in collectors:
        try:
            logger.info(f"Running collector [{collector.name}] for niche: {niche.name} (use_cache={use_cache})")
            evidence_items = collector.collect(niche, use_cache=use_cache)
            # Ensure only evidence with valid source_url is included
            valid_items = [e for e in evidence_items if e.source_url and e.source_url.strip()]
            all_evidence.extend(valid_items)
            logger.info(f"Collector [{collector.name}] produced {len(valid_items)} evidence items.")
        except Exception as e:
            logger.error(f"Collector [{collector.name}] failed for niche '{niche.name}': {e}", exc_info=True)

    return all_evidence
