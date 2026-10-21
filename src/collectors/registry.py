"""Collector registry and orchestrator."""

from __future__ import annotations
import logging
from typing import List, Type
from src.core.models import Evidence, Niche
from .base import Collector
from .google_suggest import GoogleSuggestCollector
from .google_trends import GoogleTrendsCollector
from .reddit import RedditCollector
from .web_search import WebSearchCollector

logger = logging.getLogger(__name__)

COLLECTORS: List[Type[Collector]] = [
    GoogleSuggestCollector,
    GoogleTrendsCollector,
    RedditCollector,
    WebSearchCollector,
]


def collect_for_niche(niche: Niche, collectors: List[Type[Collector]] = None) -> List[Evidence]:
    """Runs all registered collectors for a given niche.
    Gracefully handles failures per collector so the rest still run.
    """
    if collectors is None:
        collectors = COLLECTORS

    all_evidence: List[Evidence] = []

    for collector_cls in collectors:
        collector = collector_cls()
        try:
            logger.info(f"Running collector [{collector.name}] for niche: {niche.name}")
            evidence_items = collector.collect(niche)
            # Ensure only evidence with valid source_url is included
            valid_items = [e for e in evidence_items if e.source_url and e.source_url.strip()]
            all_evidence.extend(valid_items)
            logger.info(f"Collector [{collector.name}] produced {len(valid_items)} evidence items.")
        except Exception as e:
            logger.error(f"Collector [{collector.name}] failed for niche '{niche.name}': {e}", exc_info=True)

    return all_evidence
