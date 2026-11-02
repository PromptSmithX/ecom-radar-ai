"""Tests for the Amazon search-results collector."""

from __future__ import annotations
from datetime import datetime, timedelta
from unittest.mock import MagicMock
import pytest
from src.collectors.amazon import COOLDOWN_META_KEY, AmazonCollector
from src.core.cache import cache
from src.core.models import Evidence, Niche

SAMPLE_HTML = """
<html><body>
<div data-component-type="s-search-result">
  <h2><a href="/dp/B000TEST1/ref=sr_1_1"><span>Personalized Family Name Ornament</span></a></h2>
  <div class="a-row"><span class="a-icon-alt">4.7 out of 5 stars</span></div>
  <span aria-label="1,234">1,234</span>
  <span class="a-price"><span class="a-offscreen">$19.99</span></span>
  <span>Amazon's Choice</span>
</div>
<div data-component-type="s-search-result">
  <h2><a href="https://www.amazon.com/dp/B000TEST2"><span>Generic Gift Box</span></a></h2>
</div>
</body></html>
"""

CAPTCHA_HTML = "<html><body>Enter the characters you see below (captcha check)</body></html>"


@pytest.fixture
def sample_niche():
    return Niche(id="personalized_gift", name="Personalized gift", seed_keywords=["personalized gifts"])


@pytest.fixture
def cleanup_amazon_cooldown():
    yield
    meta_path = cache.raw_dir / "_meta_amazon_cooldown.json"
    meta_path.unlink(missing_ok=True)


def _fake_client(get_responses):
    """Builds a fake httpx.Client usable as a context manager, returning given responses in order."""
    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    client.get.side_effect = get_responses
    return client


def _response(status_code: int, text: str):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


def test_disabled_returns_empty(sample_niche, cleanup_amazon_cooldown):
    collector = AmazonCollector()
    collector.enabled = False
    results = collector.collect(sample_niche, use_cache=False)
    assert results == []


def test_parses_title_price_rating_and_badge(sample_niche, cleanup_amazon_cooldown):
    collector = AmazonCollector(client_factory=lambda: _fake_client([_response(200, SAMPLE_HTML)]))
    collector.enabled = True
    results = collector.collect(sample_niche, use_cache=False)

    assert len(results) == 2
    first = results[0]
    assert isinstance(first, Evidence)
    assert first.source == "amazon"
    assert first.kind == "price"
    assert first.value == "$19.99"
    assert "Personalized Family Name Ornament" in first.text
    assert "Best Seller" in first.text or "Amazon's Choice" in first.text
    assert first.source_url == "https://www.amazon.com/dp/B000TEST1/ref=sr_1_1"

    second = results[1]
    assert second.kind == "competitor"
    assert second.value is None
    assert second.source_url == "https://www.amazon.com/dp/B000TEST2"


def test_never_fabricates_price_when_missing(sample_niche, cleanup_amazon_cooldown):
    collector = AmazonCollector(client_factory=lambda: _fake_client([_response(200, SAMPLE_HTML)]))
    collector.enabled = True
    results = collector.collect(sample_niche, use_cache=False)

    no_price_item = next(ev for ev in results if ev.title == "Generic Gift Box")
    assert no_price_item.value is None


def test_captcha_sets_cooldown_and_returns_no_products(sample_niche, cleanup_amazon_cooldown):
    collector = AmazonCollector(client_factory=lambda: _fake_client([_response(200, CAPTCHA_HTML)]))
    collector.enabled = True
    results = collector.collect(sample_niche, use_cache=False)

    assert results == []
    meta = cache.get_meta(COOLDOWN_META_KEY)
    assert meta is not None
    limited_until = datetime.fromisoformat(meta["limited_until"])
    assert limited_until > datetime.now()


def test_skips_real_call_during_cooldown(sample_niche, cleanup_amazon_cooldown):
    future = datetime.now() + timedelta(minutes=10)
    cache.set_meta(COOLDOWN_META_KEY, {"limited_until": future.isoformat()})

    called = {"count": 0}

    def factory():
        called["count"] += 1
        return _fake_client([_response(200, SAMPLE_HTML)])

    collector = AmazonCollector(client_factory=factory)
    collector.enabled = True
    results = collector.collect(sample_niche, use_cache=False)

    assert results == []
    assert called["count"] == 0


def test_query_caching(sample_niche, cleanup_amazon_cooldown):
    calls = {"count": 0}

    def factory():
        calls["count"] += 1
        return _fake_client([_response(200, SAMPLE_HTML)])

    collector = AmazonCollector(client_factory=factory)
    collector.enabled = True

    first = collector.collect(sample_niche, use_cache=True)
    second = collector.collect(sample_niche, use_cache=True)

    assert len(first) == len(second) == 2
    assert calls["count"] == 1
