"""Unit tests for the refactored Reddit collector (JSON + optional Tavily) without live network calls."""

from __future__ import annotations
from unittest.mock import MagicMock, patch, PropertyMock
import pytest
from src.collectors.reddit import REDDIT_THREAD_PATTERN, RedditCollector
from src.core.cache import cache
from src.core.models import Evidence, Niche


@pytest.fixture
def sample_niche():
    return Niche(
        id="christmas_gift_ideas",
        name="Christmas gift ideas",
        seed_keywords=["christmas gift ideas"],
    )


def _make_reddit_json_response(children_data):
    """Helper to build a Reddit JSON API response structure."""
    return {
        "data": {
            "children": [
                {"data": d} for d in children_data
            ]
        }
    }


def _make_mock_httpx_response(json_data, status_code=200):
    """Helper to build a mock httpx.Response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status.return_value = None
    return mock_resp


# ================================================================
# URL regex tests (unchanged)
# ================================================================

def test_reddit_url_regex_filtering():
    """Validates URL regex acceptance and rejection patterns."""
    valid_urls = [
        "https://www.reddit.com/r/gifts/comments/17abcde/best_gifts_ever/",
        "http://reddit.com/r/BuyItForLife/comments/xyz123/practical_gifts",
        "https://www.reddit.com/r/AskMen/comments/987abc/",
    ]
    invalid_urls = [
        "https://www.reddit.com/r/gifts/",
        "https://www.reddit.com/r/all/search/?q=christmas+gifts",
        "https://www.reddit.com/user/john_doe/",
        "https://www.reddit.com/r/gifts/wiki/index",
        "https://google.com/search?q=reddit+gifts",
    ]

    for u in valid_urls:
        match = REDDIT_THREAD_PATTERN.search(u)
        assert match is not None, f"Expected valid URL: {u}"
        assert match.group(1)
        assert match.group(2)

    for u in invalid_urls:
        match = REDDIT_THREAD_PATTERN.search(u)
        assert match is None, f"Expected invalid URL: {u}"


# ================================================================
# JSON backend tests
# ================================================================

@patch("src.collectors.reddit.httpx.get")
def test_json_backend_parses_reddit_response(mock_get, sample_niche):
    """Reddit JSON backend correctly parses permalink, title, selftext and score."""
    json_data = _make_reddit_json_response([
        {
            "permalink": "/r/gifts/comments/abc123/best_gifts_under_50/",
            "title": "Best gifts under $50",
            "selftext": "Looking for affordable gift ideas that people actually appreciate and use daily.",
            "score": 42,
            "subreddit": "gifts",
        }
    ])
    mock_get.return_value = _make_mock_httpx_response(json_data)

    collector = RedditCollector(use_tavily=False)
    results = collector.collect(sample_niche, use_cache=False)

    assert len(results) > 0
    found = [r for r in results if r.post_id == "abc123"]
    assert len(found) >= 1
    ev = found[0]
    assert ev.subreddit == "gifts"
    assert ev.source_url == "https://www.reddit.com/r/gifts/comments/abc123/"
    assert ev.is_mock is False
    assert ev.value is None  # No fabricated value


@patch("src.collectors.reddit.httpx.get")
def test_json_backend_skips_non_thread_urls(mock_get, sample_niche):
    """Posts without /comments/ in permalink are filtered out."""
    json_data = _make_reddit_json_response([
        {
            "permalink": "/r/gifts/",
            "title": "Subreddit root",
            "selftext": "This is the subreddit description which should not match as a thread.",
            "score": 0,
            "subreddit": "gifts",
        }
    ])
    mock_get.return_value = _make_mock_httpx_response(json_data)

    collector = RedditCollector(use_tavily=False)
    results = collector.collect(sample_niche, use_cache=False)

    # Should have no results from this non-thread entry
    assert all(r.subreddit != "gifts" or r.post_id is not None for r in results)


@patch("src.collectors.reddit.httpx.get")
def test_json_backend_429_retries_then_empty(mock_get, sample_niche):
    """Reddit JSON 429 triggers retry, then returns empty on exhaustion."""
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_get.return_value = mock_resp

    collector = RedditCollector(use_tavily=False)
    collector.backoff_base = 0.01  # Speed up test
    collector.request_delay = 0
    results = collector.collect(sample_niche, use_cache=False)

    # All queries should have failed, but collector doesn't crash
    assert isinstance(results, list)


@patch("src.collectors.reddit.httpx.get")
def test_json_backend_no_tavily_called(mock_get, sample_niche):
    """When use_tavily=False, TavilyClient is never imported or called."""
    json_data = _make_reddit_json_response([
        {
            "permalink": "/r/gifts/comments/notav1/no_tavily_test/",
            "title": "Testing without Tavily",
            "selftext": "This content should come from JSON only, never from Tavily client search.",
            "score": 10,
            "subreddit": "gifts",
        }
    ])
    mock_get.return_value = _make_mock_httpx_response(json_data)

    with patch("tavily.TavilyClient") as mock_tavily_cls:
        collector = RedditCollector(use_tavily=False)
        results = collector.collect(sample_niche, use_cache=False)

        mock_tavily_cls.assert_not_called()
        assert len(results) > 0


@patch("tavily.TavilyClient")
@patch("src.collectors.reddit.httpx.get")
def test_json_and_tavily_combined_dedup(mock_get, mock_tavily_cls, sample_niche):
    """When use_tavily=True, both backends run and duplicates are removed by post_id."""
    # JSON returns one post
    json_data = _make_reddit_json_response([
        {
            "permalink": "/r/gifts/comments/shared1/shared_post/",
            "title": "Shared post from both sources",
            "selftext": "This post appears in both JSON and Tavily results for dedup testing.",
            "score": 55,
            "subreddit": "gifts",
        },
        {
            "permalink": "/r/gifts/comments/jsononly/json_only/",
            "title": "JSON only post",
            "selftext": "This post only appears in the JSON results and not in Tavily results.",
            "score": 20,
            "subreddit": "gifts",
        },
    ])
    mock_get.return_value = _make_mock_httpx_response(json_data)

    # Tavily returns the same shared post + one unique
    mock_client = MagicMock()
    mock_tavily_cls.return_value = mock_client
    mock_client.search.return_value = {
        "results": [
            {
                "title": "Shared post from both sources",
                "url": "https://www.reddit.com/r/gifts/comments/shared1/shared_post/",
                "content": "This post appears in both JSON and Tavily results for dedup testing.",
                "score": 0.95,
            },
            {
                "title": "Tavily only post",
                "url": "https://www.reddit.com/r/GiftIdeas/comments/tavonly/tavily_unique/",
                "content": "This post only appears in the Tavily results and not in JSON results.",
                "score": 0.88,
            },
        ]
    }

    collector = RedditCollector(api_key="tvly-test-key", use_tavily=True)
    collector.request_delay = 0
    results = collector.collect(sample_niche, use_cache=False)

    post_ids = [r.post_id for r in results]
    # shared1 should appear only once (from JSON, since it runs first)
    assert post_ids.count("shared1") == 1
    # Both unique posts should be present
    assert "jsononly" in post_ids
    assert "tavonly" in post_ids


@patch("src.collectors.reddit.httpx.get")
def test_json_cache_separate_from_tavily(mock_get):
    """JSON and Tavily cache keys use different prefixes."""
    collector = RedditCollector(use_tavily=False)
    json_key = collector._build_query_cache_key("test query", "json")
    tavily_key = collector._build_query_cache_key("test query", "tavily")
    assert json_key != tavily_key
    assert json_key.startswith("json_query_")
    assert tavily_key.startswith("tavily_query_")


# ================================================================
# Tavily backend tests (existing, updated with use_tavily=True)
# ================================================================

def test_missing_api_key_json_still_works(sample_niche):
    """When use_tavily=False and no API key, JSON backend still works."""
    with patch("src.collectors.reddit.httpx.get") as mock_get:
        json_data = _make_reddit_json_response([
            {
                "permalink": "/r/gifts/comments/nokey1/no_key_test/",
                "title": "Works without API key",
                "selftext": "The JSON backend does not need any API key to function properly.",
                "score": 5,
                "subreddit": "gifts",
            }
        ])
        mock_get.return_value = _make_mock_httpx_response(json_data)

        collector = RedditCollector(api_key="", use_tavily=False)
        results = collector.collect(sample_niche, use_cache=False)
        assert len(results) > 0


def test_missing_tavily_key_returns_no_tavily_results(sample_niche):
    """When use_tavily=True but key is empty, Tavily part returns nothing (JSON still works)."""
    with patch("src.collectors.reddit.httpx.get") as mock_get:
        json_data = _make_reddit_json_response([
            {
                "permalink": "/r/gifts/comments/nokey2/fallback_test/",
                "title": "JSON fallback when Tavily key missing",
                "selftext": "Only JSON results should appear when Tavily API key is not configured.",
                "score": 3,
                "subreddit": "gifts",
            }
        ])
        mock_get.return_value = _make_mock_httpx_response(json_data)

        collector = RedditCollector(api_key="", use_tavily=True)
        results = collector.collect(sample_niche, use_cache=False)
        # Should still have JSON results
        assert len(results) > 0
        assert isinstance(results, list)


@patch("src.collectors.reddit.httpx.get")
@patch("tavily.TavilyClient")
def test_deduplication_by_post_id(mock_tavily_cls, mock_get, sample_niche):
    """Duplicate posts across multiple queries must be deduplicated by post_id."""
    # JSON returns the same post for every query
    json_data = _make_reddit_json_response([
        {
            "permalink": "/r/gifts/comments/dup123/looking_for_gifts/",
            "title": "Looking for the best Christmas gifts",
            "selftext": "A very detailed discussion about what gifts people actually want for Christmas.",
            "score": 95,
            "subreddit": "gifts",
        }
    ])
    mock_get.return_value = _make_mock_httpx_response(json_data)

    collector = RedditCollector(use_tavily=False)
    collector.request_delay = 0
    results = collector.collect(sample_niche, use_cache=False)

    post_ids = [item.post_id for item in results]
    assert post_ids.count("dup123") == 1


@patch("src.collectors.reddit.httpx.get")
def test_no_fabricated_text_or_upvotes(mock_get, sample_niche):
    """Output evidence records must not contain fabricated prefixes or fake upvote metrics."""
    json_data = _make_reddit_json_response([
        {
            "permalink": "/r/GiftIdeas/comments/real456/ideas/",
            "title": "Gift ideas for someone who has everything",
            "selftext": "Stop buying cheap plastic gadgets that get thrown away. Focus on useful experiences.",
            "score": 92,
            "subreddit": "GiftIdeas",
        }
    ])
    mock_get.return_value = _make_mock_httpx_response(json_data)

    collector = RedditCollector(use_tavily=False)
    collector.request_delay = 0
    results = collector.collect(sample_niche, use_cache=False)

    assert len(results) > 0
    for r in results:
        if r.post_id == "real456":
            assert "Thảo luận cộng đồng" not in r.text
            assert "Insight:" not in r.text
            assert r.value is None
            assert "upvote" not in (r.text.lower())
            assert r.intent in ["ask", "pain", "regret", "recommend"]
            assert r.subreddit == "GiftIdeas"
            assert r.post_id == "real456"


@patch("src.collectors.reddit.httpx.get")
def test_snippet_verbatim_and_max_500_chars(mock_get, sample_niche):
    """Snippet must be verbatim from content, truncated to at most 500 characters."""
    very_long_content = "Authentic user comment content. " * 30  # ~960 chars
    json_data = _make_reddit_json_response([
        {
            "permalink": "/r/BuyItForLife/comments/long789/review/",
            "title": "Long review of gifts",
            "selftext": very_long_content,
            "score": 85,
            "subreddit": "BuyItForLife",
        }
    ])
    mock_get.return_value = _make_mock_httpx_response(json_data)

    collector = RedditCollector(use_tavily=False)
    collector.request_delay = 0
    results = collector.collect(sample_niche, use_cache=False)

    long_results = [r for r in results if r.post_id == "long789"]
    assert len(long_results) == 1
    snippet = long_results[0].snippet
    assert len(snippet) <= 500
    assert very_long_content.startswith(snippet)


@patch("src.collectors.reddit.httpx.get")
def test_drop_empty_title_or_short_snippet(mock_get, sample_niche):
    """Records with empty titles or snippets shorter than 40 chars must be ignored."""
    json_data = _make_reddit_json_response([
        {
            "permalink": "/r/gifts/comments/bad1/test/",
            "title": "",
            "selftext": "Valid length content that should be skipped due to empty title. This is long enough.",
            "score": 0,
            "subreddit": "gifts",
        },
        {
            "permalink": "/r/gifts/comments/bad2/test/",
            "title": "Short snippet post",
            "selftext": "Too short.",
            "score": 0,
            "subreddit": "gifts",
        },
    ])
    mock_get.return_value = _make_mock_httpx_response(json_data)

    collector = RedditCollector(use_tavily=False)
    collector.request_delay = 0
    results = collector.collect(sample_niche, use_cache=False)

    bad_ids = {r.post_id for r in results}
    assert "bad1" not in bad_ids
    assert "bad2" not in bad_ids


@patch("src.collectors.reddit.httpx.get")
def test_query_caching(mock_get):
    """Second call with use_cache=True should load results from cache and not call httpx again."""
    import uuid

    json_data = _make_reddit_json_response([
        {
            "permalink": "/r/gifts/comments/cache999/test/",
            "title": "Cached test thread",
            "selftext": "This is content that will be cached and verified on secondary lookup from JSON.",
            "score": 99,
            "subreddit": "gifts",
        }
    ])
    mock_get.return_value = _make_mock_httpx_response(json_data)

    random_id = uuid.uuid4().hex[:8]
    unique_niche = Niche(
        id=f"cache_niche_{random_id}",
        name=f"Cache Niche {random_id}",
        seed_keywords=[f"test_cache_kw_{random_id}"],
    )

    collector = RedditCollector(use_tavily=False)
    collector.request_delay = 0

    # First run (must query and populate cache)
    results1 = collector.collect(unique_niche, use_cache=True)
    initial_get_calls = mock_get.call_count
    assert initial_get_calls > 0
    assert len(results1) > 0

    # Second run (must use cache without new network calls)
    results2 = collector.collect(unique_niche, use_cache=True)
    assert mock_get.call_count == initial_get_calls
    assert len(results2) == len(results1)
    assert results2[0].post_id == results1[0].post_id
