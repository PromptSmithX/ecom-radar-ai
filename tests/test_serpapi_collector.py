"""Tests for the SerpApi Trends collector (Google Trends via SerpApi)."""

from __future__ import annotations
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pytest
from src.collectors.registry import TREND_PROVIDERS, build_collectors
from src.collectors.serpapi_trends import COOLDOWN_META_KEY, SerpApiTrendsCollector
from src.collectors.google_trends import GoogleTrendsCollector
from src.core.cache import cache
from src.core.models import Evidence, Niche


@pytest.fixture
def sample_niche():
    return Niche(
        id="christmas_gift_ideas",
        name="Christmas gift ideas",
        seed_keywords=["christmas gift ideas", "stocking stuffers"],
    )


@pytest.fixture
def cleanup_serpapi_cooldown():
    yield
    meta_path = cache.raw_dir / "_meta_serpapi_trends_cooldown.json"
    meta_path.unlink(missing_ok=True)


def _mock_response(json_payload: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_payload
    return resp


def test_missing_api_key_returns_empty_list(sample_niche, cleanup_serpapi_cooldown):
    collector = SerpApiTrendsCollector(api_key="")
    results = collector.collect(sample_niche, use_cache=False)
    assert results == []


@patch("src.collectors.serpapi_trends.httpx.Client")
def test_success_path(mock_client_cls, sample_niche, cleanup_serpapi_cooldown):
    mock_client = MagicMock()
    mock_client.get.return_value = _mock_response(
        {
            "related_queries": {
                "rising": [{"query": "stocking stuffers for men", "extracted_value": 120}],
                "top": [{"query": "best stocking stuffers", "extracted_value": 85}],
            }
        }
    )
    mock_client_cls.return_value.__enter__.return_value = mock_client

    collector = SerpApiTrendsCollector(api_key="serp-test-key")
    results = collector.collect(sample_niche, use_cache=False)

    assert len(results) > 0
    for ev in results:
        assert isinstance(ev, Evidence)
        assert ev.source == "serpapi_trends"
        assert ev.is_mock is False
        assert ev.source_url.startswith("https://trends.google.com")


@patch("src.collectors.serpapi_trends.httpx.Client")
def test_429_sets_cooldown_and_fallback(mock_client_cls, sample_niche, cleanup_serpapi_cooldown):
    mock_client = MagicMock()
    mock_client.get.return_value = _mock_response({}, status_code=429)
    mock_client_cls.return_value.__enter__.return_value = mock_client

    collector = SerpApiTrendsCollector(api_key="serp-test-key")
    results = collector.collect(sample_niche, use_cache=False)

    assert len(results) > 0
    assert all(ev.is_mock for ev in results)

    meta = cache.get_meta(COOLDOWN_META_KEY)
    assert meta is not None
    limited_until = datetime.fromisoformat(meta["limited_until"])
    assert limited_until > datetime.now()


def test_skips_real_call_during_cooldown(sample_niche, cleanup_serpapi_cooldown):
    future = datetime.now() + timedelta(minutes=30)
    cache.set_meta(COOLDOWN_META_KEY, {"limited_until": future.isoformat()})

    collector = SerpApiTrendsCollector(api_key="serp-test-key")
    with patch("src.collectors.serpapi_trends.httpx.Client") as mock_client_cls:
        results = collector.collect(sample_niche, use_cache=False)
        mock_client_cls.assert_not_called()

    assert len(results) > 0
    assert all(ev.is_mock for ev in results)


def test_build_collectors_selects_provider():
    google_instances = build_collectors("google_trends")
    assert any(isinstance(c, GoogleTrendsCollector) for c in google_instances)
    assert not any(isinstance(c, SerpApiTrendsCollector) for c in google_instances)

    serp_instances = build_collectors("serpapi", trend_api_key="serp-test-key")
    serp_collector = next(c for c in serp_instances if isinstance(c, SerpApiTrendsCollector))
    assert serp_collector.api_key == "serp-test-key"
    assert not any(isinstance(c, GoogleTrendsCollector) for c in serp_instances)


def test_trend_providers_registry():
    assert set(TREND_PROVIDERS.keys()) == {"google_trends", "serpapi"}
