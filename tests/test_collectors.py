"""Tests for data collectors."""

from __future__ import annotations
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest
from src.collectors.amazon import AmazonCollector
from src.collectors.base import Collector
from src.collectors.etsy import EtsyCollector
from src.collectors.google_suggest import GoogleSuggestCollector
from src.collectors.google_trends import COOLDOWN_META_KEY, GoogleTrendsCollector
from src.collectors.reddit import RedditCollector
from src.collectors.registry import COLLECTORS, build_collectors, collect_for_niche
from src.collectors.web_search import WebSearchCollector
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


@patch("src.collectors.google_suggest.httpx.Client")
def test_google_suggest_collector(mock_client_cls, sample_niche):
    """Google Suggest returns suggestions via the (mocked) HTTP client, no live network call."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = ["christmas gift ideas", ["christmas gift ideas for mom", "christmas gift ideas for dad"]]
    mock_client.get.return_value = mock_resp

    collector = GoogleSuggestCollector()
    collector.request_delay = 0
    results = collector.collect(sample_niche, use_cache=False)
    assert isinstance(results, list)
    assert len(results) > 0
    for item in results:
        assert isinstance(item, Evidence)
        assert item.source == "google_suggest"
        assert item.source_url.startswith("http")
        assert item.kind == "keyword_signal"
        assert "Google Autocomplete" in item.text


def test_reddit_collector(sample_niche):
    """RedditCollector sources Reddit threads with BrowserManager."""
    mock_browser = MagicMock()
    mock_browser.fetch_page_content.return_value = """
    <html><body>
    <div>
      <a href="/r/gifts/comments/abc123/best_gifts/">Best Christmas gifts under $50</a>
      <span>350 votes · 45 comments</span>
    </div>
    <div>
      <a href="/r/gifts/comments/abc456/ideas/">Great holiday ideas</a>
      <span>200 votes · 15 comments</span>
    </div>
    <div>
      <a href="/r/gifts/comments/abc789/unique/">Unique stocking stuffers</a>
      <span>120 votes · 10 comments</span>
    </div>
    </body></html>
    """
    collector = RedditCollector(browser_manager=mock_browser)
    results = collector.collect(sample_niche, use_cache=False)
    assert isinstance(results, list)
    assert len(results) >= 3
    first = results[0]
    assert isinstance(first, Evidence)
    assert first.source == "reddit"
    assert first.source_url.startswith("http")
    assert first.post_id == "abc123"
    assert first.subreddit == "gifts"


def test_web_search_collector(sample_niche):
    mock_results = [
        {
            "title": "Top Gift Guide 2026",
            "href": "https://example.com/guide",
            "body": "Best gifts and prices for everyone on your list.",
        }
    ]
    with patch("src.collectors.web_search.DDGS") as mock_ddgs:
        inst = MagicMock()
        mock_ddgs.return_value = inst
        inst.text.return_value = mock_results

        collector = WebSearchCollector()
        results = collector.collect(sample_niche, use_cache=False)
        assert isinstance(results, list)
        assert len(results) > 0
        for item in results:
            assert isinstance(item, Evidence)
            assert item.source == "web_search"
            assert item.source_url.startswith("http")


@pytest.fixture
def cleanup_trends_cooldown():
    """Ensures the Google Trends circuit-breaker state never leaks across tests."""
    yield
    meta_path = cache.raw_dir / f"_meta_{COOLDOWN_META_KEY}.json"
    meta_path.unlink(missing_ok=True)


def test_google_trends_success_path(cleanup_trends_cooldown):
    mock_client = MagicMock()
    df_top = pd.DataFrame([{"query": "best gift", "value": 100}])
    df_rising = pd.DataFrame([{"query": "cozy gift", "value": 250}])
    mock_client.related_queries.return_value = {"gift": {"top": df_top, "rising": df_rising}}

    collector = GoogleTrendsCollector(trend_client_factory=lambda: mock_client)
    collector.sleep_seconds = 0
    niche = Niche(id="t1", name="Gift", seed_keywords=["gift"])
    results = collector.collect(niche, use_cache=False)

    assert len(results) > 0
    assert any(ev.keyword == "cozy gift" and "+250%" in ev.text for ev in results)


def test_google_trends_429_sets_cooldown_and_fallback(cleanup_trends_cooldown):
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


def test_build_collectors_includes_all_sources():
    collectors = build_collectors(use_amazon=True, use_etsy=True)
    collector_types = [type(c) for c in collectors]
    assert WebSearchCollector in collector_types
    assert RedditCollector in collector_types
    assert AmazonCollector in collector_types
    assert EtsyCollector in collector_types
    assert GoogleSuggestCollector in collector_types


def test_build_collectors_can_toggle_amazon_and_etsy():
    collectors = build_collectors(use_amazon=False, use_etsy=False)
    collector_types = [type(c) for c in collectors]
    assert AmazonCollector not in collector_types
    assert EtsyCollector not in collector_types
    assert RedditCollector in collector_types
    assert WebSearchCollector in collector_types
