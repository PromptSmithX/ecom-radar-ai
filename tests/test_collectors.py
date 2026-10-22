"""Tests for data collectors."""

from __future__ import annotations
from datetime import datetime, timedelta
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch
from src.collectors.base import Collector
from src.collectors.google_suggest import GoogleSuggestCollector
from src.collectors.google_trends import COOLDOWN_META_KEY, GoogleTrendsCollector
from src.collectors.reddit import RedditCollector
from src.collectors.web_search import WebSearchCollector
from src.collectors.registry import build_collectors, collect_for_niche, COLLECTORS
from src.core.cache import cache
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


@patch("src.collectors.reddit.httpx.get")
def test_reddit_collector(mock_get, sample_niche):
    """RedditCollector with JSON backend (default) parses results correctly."""
    json_data = {
        "data": {
            "children": [
                {
                    "data": {
                        "permalink": "/r/gifts/comments/abc123/best_gifts/",
                        "title": "Best Christmas gifts under $50",
                        "selftext": "Authentic feedback about quality gifts that do not break the bank for the holidays.",
                        "score": 42,
                        "subreddit": "gifts",
                    }
                }
            ]
        }
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    collector = RedditCollector(use_tavily=False)
    collector.request_delay = 0
    results = collector.collect(sample_niche, use_cache=False)
    assert isinstance(results, list)
    assert len(results) > 0
    for item in results:
        assert isinstance(item, Evidence)
        assert item.source == "reddit"
        assert item.source_url.startswith("http")
        assert item.post_id == "abc123"
        assert item.subreddit == "gifts"
        assert item.value is None


def test_web_search_collector(sample_niche):
    collector = WebSearchCollector()
    results = collector.collect(sample_niche)
    assert isinstance(results, list)
    assert len(results) > 0
    for item in results:
        assert isinstance(item, Evidence)
        assert item.source == "web_search"
        assert item.source_url.startswith("http")


@pytest.fixture
def cleanup_trends_cooldown():
    """Ensures the Google Trends circuit-breaker state never leaks across tests or into
    real dev runs."""
    yield
    meta_path = cache.raw_dir / "_meta_google_trends_cooldown.json"
    meta_path.unlink(missing_ok=True)


def test_google_trends_success_path(cleanup_trends_cooldown):
    """A fully mocked TrendReq client lets us test the happy path with no network call."""
    mock_client = MagicMock()
    mock_client.related_queries.return_value = {
        "christmas gift ideas": {
            "rising": pd.DataFrame({"query": ["stocking stuffers for men"], "value": [120]}),
            "top": pd.DataFrame({"query": ["best stocking stuffers"], "value": [85]}),
        }
    }
    mock_client.interest_over_time.return_value = pd.DataFrame(
        {"christmas gift ideas": [10, 12, 15, 40, 45, 50]}
    )

    collector = GoogleTrendsCollector(trend_client_factory=lambda: mock_client)
    collector.sleep_seconds = 0
    niche = Niche(id="t1", name="Christmas gift ideas", seed_keywords=["christmas gift ideas"])
    results = collector.collect(niche, use_cache=False)

    assert len(results) > 0
    for ev in results:
        assert isinstance(ev, Evidence)
        assert ev.source == "google_trends"
        assert ev.is_mock is False


def test_google_trends_429_sets_cooldown_and_fallback(cleanup_trends_cooldown):
    """A 429 from the client must trigger the baseline fallback AND persist a cooldown."""
    mock_client = MagicMock()
    mock_client.build_payload.side_effect = Exception("429 Too Many Requests")

    collector = GoogleTrendsCollector(trend_client_factory=lambda: mock_client)
    collector.sleep_seconds = 0
    niche = Niche(id="t2", name="Gift for him", seed_keywords=["gifts for him"])
    results = collector.collect(niche, use_cache=False)

    assert len(results) > 0
    assert all(ev.is_mock for ev in results)

    meta = cache.get_meta(COOLDOWN_META_KEY)
    assert meta is not None
    limited_until = datetime.fromisoformat(meta["limited_until"])
    assert limited_until > datetime.now()


def test_google_trends_skips_real_call_during_cooldown(cleanup_trends_cooldown):
    """While a cooldown is active, the real client must never even be constructed."""
    future = datetime.now() + timedelta(minutes=30)
    cache.set_meta(COOLDOWN_META_KEY, {"limited_until": future.isoformat()})

    def factory():
        raise AssertionError("Real Trends client should not be instantiated during cooldown")

    collector = GoogleTrendsCollector(trend_client_factory=factory)
    collector.sleep_seconds = 0
    niche = Niche(id="t3", name="Valentine gift", seed_keywords=["valentine gifts"])
    results = collector.collect(niche, use_cache=False)

    assert len(results) > 0
    assert all(ev.is_mock for ev in results)


def test_build_collectors_excludes_websearch_without_tavily():
    """When use_tavily=False (default), WebSearchCollector is not included."""
    collectors = build_collectors(use_tavily=False)
    collector_types = [type(c) for c in collectors]
    assert WebSearchCollector not in collector_types
    assert RedditCollector in collector_types
    # Verify RedditCollector has use_tavily=False
    reddit = [c for c in collectors if isinstance(c, RedditCollector)][0]
    assert reddit.use_tavily is False


def test_build_collectors_includes_websearch_with_tavily():
    """When use_tavily=True, WebSearchCollector is included."""
    collectors = build_collectors(use_tavily=True)
    collector_types = [type(c) for c in collectors]
    assert WebSearchCollector in collector_types
    assert RedditCollector in collector_types
    # Verify RedditCollector has use_tavily=True
    reddit = [c for c in collectors if isinstance(c, RedditCollector)][0]
    assert reddit.use_tavily is True


def test_registry_collect_for_niche(sample_niche):
    # Test registry execution without crashing even if network/rate-limits happen
    all_evidence = collect_for_niche(sample_niche)
    assert isinstance(all_evidence, list)
    assert len(all_evidence) > 0
    # Every item must have a non-empty source_url
    for item in all_evidence:
        assert item.source_url and item.source_url.strip()
