"""Tests for data collectors."""

from __future__ import annotations
import pytest
from src.collectors.base import Collector
from src.collectors.google_suggest import GoogleSuggestCollector
from src.collectors.google_trends import GoogleTrendsCollector
from src.collectors.reddit import RedditCollector
from src.collectors.web_search import WebSearchCollector
from src.collectors.registry import collect_for_niche, COLLECTORS
from src.core.models import Evidence, Niche


@pytest.fixture
def sample_niche():
    return Niche(
        id="christmas_gift_ideas",
        name="Christmas gift ideas",
        seed_keywords=["christmas gift ideas", "stocking stuffers"],
    )


def test_collectors_inheritance():
    for cls in COLLECTORS:
        assert issubclass(cls, Collector)
        assert hasattr(cls, "name")


def test_google_suggest_collector(sample_niche):
    collector = GoogleSuggestCollector()
    results = collector.collect(sample_niche)
    assert isinstance(results, list)
    assert len(results) > 0
    for item in results:
        assert isinstance(item, Evidence)
        assert item.source == "google_suggest"
        assert item.source_url.startswith("http")
        assert item.kind == "keyword_signal"


def test_reddit_collector(sample_niche):
    collector = RedditCollector()
    results = collector.collect(sample_niche)
    assert isinstance(results, list)
    assert len(results) > 0
    for item in results:
        assert isinstance(item, Evidence)
        assert item.source == "reddit"
        assert item.source_url.startswith("http")


def test_web_search_collector(sample_niche):
    collector = WebSearchCollector()
    results = collector.collect(sample_niche)
    assert isinstance(results, list)
    assert len(results) > 0
    for item in results:
        assert isinstance(item, Evidence)
        assert item.source == "web_search"
        assert item.source_url.startswith("http")


def test_registry_collect_for_niche(sample_niche):
    # Test registry execution without crashing even if network/rate-limits happen
    all_evidence = collect_for_niche(sample_niche)
    assert isinstance(all_evidence, list)
    assert len(all_evidence) > 0
    # Every item must have a non-empty source_url
    for item in all_evidence:
        assert item.source_url and item.source_url.strip()
