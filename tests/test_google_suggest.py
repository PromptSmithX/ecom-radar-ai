"""Unit tests for the GoogleSuggestCollector fallback chain (Google -> DuckDuckGo -> Bing).

All tests mock httpx.Client — no live network calls.
"""

from __future__ import annotations
from unittest.mock import MagicMock, patch
import pytest
from src.collectors.google_suggest import GoogleSuggestCollector
from src.core.models import Niche


@pytest.fixture
def sample_niche():
    return Niche(
        id="christmas_gift_ideas",
        name="Christmas gift ideas",
        seed_keywords=["christmas gift ideas"],
    )


def _ok_response(suggestions):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = ["q", suggestions]
    return resp


def _rate_limited_response():
    resp = MagicMock()
    resp.status_code = 429
    resp.json.return_value = {}
    return resp


@patch("src.collectors.google_suggest.httpx.Client")
def test_google_success_no_fallback(mock_client_cls, sample_niche):
    """When Google answers successfully, DuckDuckGo and Bing must never be called."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_client.get.return_value = _ok_response(["christmas gift ideas for mom"])

    collector = GoogleSuggestCollector()
    collector.request_delay = 0
    results = collector.collect(sample_niche, use_cache=False)

    assert len(results) > 0
    assert mock_client.get.call_count == 1  # only Google was queried
    assert "Google Autocomplete" in results[0].text


@patch("src.collectors.google_suggest.httpx.Client")
def test_google_429_falls_back_to_ddg(mock_client_cls, sample_niche):
    """When Google returns 429, the collector falls back to DuckDuckGo and the
    evidence text names DuckDuckGo, not Google."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    def side_effect(url, params=None):
        if "google" in url:
            return _rate_limited_response()
        return _ok_response(["christmas gift ideas for dad"])

    mock_client.get.side_effect = side_effect

    collector = GoogleSuggestCollector()
    collector.request_delay = 0
    results = collector.collect(sample_niche, use_cache=False)

    assert len(results) > 0
    assert "DuckDuckGo Autocomplete" in results[0].text
    assert "Google Autocomplete" not in results[0].text


@patch("src.collectors.google_suggest.httpx.Client")
def test_ddg_fails_falls_back_to_bing(mock_client_cls, sample_niche):
    """When both Google and DuckDuckGo fail, the collector falls back to Bing."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    def side_effect(url, params=None):
        if "bing" in url:
            return _ok_response(["christmas gift ideas for kids"])
        return _rate_limited_response()

    mock_client.get.side_effect = side_effect

    collector = GoogleSuggestCollector()
    collector.request_delay = 0
    results = collector.collect(sample_niche, use_cache=False)

    assert len(results) > 0
    assert "Bing Autocomplete" in results[0].text


@patch("src.collectors.google_suggest.httpx.Client")
def test_all_providers_fail_returns_empty(mock_client_cls, sample_niche):
    """When all three providers fail, the collector returns an empty list without crashing."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_client.get.return_value = _rate_limited_response()

    collector = GoogleSuggestCollector()
    collector.request_delay = 0
    results = collector.collect(sample_niche, use_cache=False)

    assert results == []


@patch("src.collectors.google_suggest.httpx.Client")
def test_evidence_names_actual_provider(mock_client_cls, sample_niche):
    """The provider named in evidence.text must match whichever provider actually
    answered — this keeps the anti-hallucination guarantee: never attribute data
    to a source that didn't produce it."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    def side_effect(url, params=None):
        if "duckduckgo" in url:
            return _ok_response(["christmas gift ideas cheap"])
        return _rate_limited_response()

    mock_client.get.side_effect = side_effect

    collector = GoogleSuggestCollector()
    collector.request_delay = 0
    results = collector.collect(sample_niche, use_cache=False)

    assert len(results) > 0
    for ev in results:
        assert "DuckDuckGo Autocomplete" in ev.text
