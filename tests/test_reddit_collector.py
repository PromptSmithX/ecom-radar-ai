"""Unit tests for the refactored Reddit collector without making live network calls."""

from __future__ import annotations
from unittest.mock import MagicMock, patch
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
        assert match.group(1)  # Subreddit
        assert match.group(2)  # Post ID

    for u in invalid_urls:
        match = REDDIT_THREAD_PATTERN.search(u)
        assert match is None, f"Expected invalid URL: {u}"


def test_missing_api_key_returns_empty(sample_niche):
    """When TAVILY_API_KEY is missing, collector must return empty list without crashing or falling back to fake data."""
    collector = RedditCollector(api_key="")
    results = collector.collect(sample_niche, use_cache=False)
    assert results == []
    assert isinstance(results, list)

    with patch("src.collectors.reddit.settings.tavily_api_key", ""):
        collector_no_key = RedditCollector(api_key=None)
        assert collector_no_key.collect(sample_niche, use_cache=False) == []


@patch("tavily.TavilyClient")
def test_deduplication_by_post_id(mock_tavily_cls, sample_niche):
    """Duplicate posts across multiple queries must be deduplicated by post_id."""
    mock_client = MagicMock()
    mock_tavily_cls.return_value = mock_client

    # Return the exact same post for every query
    duplicate_result = {
        "title": "Looking for the best Christmas gifts",
        "url": "https://www.reddit.com/r/gifts/comments/dup123/looking_for_gifts/",
        "content": "A very detailed discussion about what gifts people actually want for Christmas this year.",
        "score": 0.95,
    }
    mock_client.search.return_value = {"results": [duplicate_result]}

    collector = RedditCollector(api_key="tvly-mock-key")
    results = collector.collect(sample_niche, use_cache=False)

    post_ids = [item.post_id for item in results]
    assert len(post_ids) == 1
    assert post_ids[0] == "dup123"


@patch("tavily.TavilyClient")
def test_resilience_to_single_query_failure(mock_tavily_cls, sample_niche):
    """A failure in one query must not crash the entire collector; subsequent queries still run."""
    mock_client = MagicMock()
    mock_tavily_cls.return_value = mock_client

    call_count = 0

    def side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Temporary network timeout")
        return {
            "results": [
                {
                    "title": f"Valid thread number {call_count}",
                    "url": f"https://www.reddit.com/r/gifts/comments/post{call_count}/test/",
                    "content": "This is a detailed authentic snippet that exceeds forty characters.",
                    "score": 0.88,
                }
            ]
        }

    mock_client.search.side_effect = side_effect

    collector = RedditCollector(api_key="tvly-mock-key")
    results = collector.collect(sample_niche, use_cache=False)

    assert len(results) > 0
    assert all(isinstance(r, Evidence) for r in results)


@patch("tavily.TavilyClient")
def test_no_fabricated_text_or_upvotes(mock_tavily_cls, sample_niche):
    """Output evidence records must not contain fabricated prefixes or fake upvote metrics."""
    mock_client = MagicMock()
    mock_tavily_cls.return_value = mock_client

    mock_client.search.return_value = {
        "results": [
            {
                "title": "Gift ideas for someone who has everything",
                "url": "https://www.reddit.com/r/GiftIdeas/comments/real456/ideas/",
                "content": "Stop buying cheap plastic gadgets that get thrown away. Focus on useful experiences.",
                "score": 0.92,
            }
        ]
    }

    collector = RedditCollector(api_key="tvly-mock-key")
    results = collector.collect(sample_niche, use_cache=False)

    assert len(results) > 0
    for r in results:
        # Check absence of fabricated strings
        assert "Thảo luận cộng đồng" not in r.text
        assert "Insight:" not in r.text
        assert r.value is None
        assert "upvote" not in (r.text.lower())
        assert r.intent in ["ask", "pain", "regret", "recommend"]
        assert r.subreddit == "GiftIdeas"
        assert r.post_id == "real456"
        assert r.relevance == 0.92


@patch("tavily.TavilyClient")
def test_snippet_verbatim_and_max_500_chars(mock_tavily_cls, sample_niche):
    """Snippet must be verbatim from Tavily content, truncated to at most 500 characters."""
    mock_client = MagicMock()
    mock_tavily_cls.return_value = mock_client

    very_long_content = "Authentic user comment content. " * 30  # ~960 chars
    mock_client.search.return_value = {
        "results": [
            {
                "title": "Long review of gifts",
                "url": "https://www.reddit.com/r/BuyItForLife/comments/long789/review/",
                "content": very_long_content,
                "score": 0.85,
            }
        ]
    }

    collector = RedditCollector(api_key="tvly-mock-key")
    results = collector.collect(sample_niche, use_cache=False)

    assert len(results) == 1
    snippet = results[0].snippet
    assert len(snippet) <= 500
    assert very_long_content.startswith(snippet)


@patch("tavily.TavilyClient")
def test_drop_empty_title_or_short_snippet(mock_tavily_cls, sample_niche):
    """Records with empty titles or snippets shorter than 40 chars must be ignored."""
    mock_client = MagicMock()
    mock_tavily_cls.return_value = mock_client

    mock_client.search.return_value = {
        "results": [
            {
                "title": "",
                "url": "https://www.reddit.com/r/gifts/comments/bad1/test/",
                "content": "Valid length content that should be skipped due to empty title.",
            },
            {
                "title": "Short snippet post",
                "url": "https://www.reddit.com/r/gifts/comments/bad2/test/",
                "content": "Too short.",
            },
        ]
    }

    collector = RedditCollector(api_key="tvly-mock-key")
    results = collector.collect(sample_niche, use_cache=False)
    assert len(results) == 0


@patch("tavily.TavilyClient")
def test_query_caching(mock_tavily_cls):
    """Second call with use_cache=True should load results from cache and not call Tavily again."""
    import uuid
    mock_client = MagicMock()
    mock_tavily_cls.return_value = mock_client

    mock_client.search.return_value = {
        "results": [
            {
                "title": "Cached test thread",
                "url": "https://www.reddit.com/r/gifts/comments/cache999/test/",
                "content": "This is content that will be cached and verified on secondary lookup.",
                "score": 0.99,
            }
        ]
    }

    random_id = uuid.uuid4().hex[:8]
    unique_niche = Niche(
        id=f"cache_niche_{random_id}",
        name=f"Cache Niche {random_id}",
        seed_keywords=[f"test_cache_kw_{random_id}"],
    )

    collector = RedditCollector(api_key="tvly-mock-key")
    # First run (must query and populate cache)
    results1 = collector.collect(unique_niche, use_cache=True)
    initial_search_calls = mock_client.search.call_count
    assert initial_search_calls > 0
    assert len(results1) > 0

    # Second run (must use cache without new network calls)
    results2 = collector.collect(unique_niche, use_cache=True)
    assert mock_client.search.call_count == initial_search_calls
    assert len(results2) == len(results1)
    assert results2[0].post_id == results1[0].post_id
