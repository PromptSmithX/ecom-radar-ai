"""Unit tests for the Reddit collector (Tavily-backed) without making live network calls.

Reddit's own public search now requires login (old.reddit.com/search.json redirects to
/login), so Tavily is the only working source. These tests mock tavily.TavilyClient.
"""

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


def test_use_tavily_false_returns_empty(sample_niche):
    """When use_tavily=False, no Reddit source is available: must return empty without
    ever touching TavilyClient."""
    with patch("tavily.TavilyClient") as mock_tavily_cls:
        collector = RedditCollector(api_key="tvly-mock-key", use_tavily=False)
        results = collector.collect(sample_niche, use_cache=False)
        assert results == []
        mock_tavily_cls.assert_not_called()


def test_missing_api_key_returns_empty(sample_niche):
    """When TAVILY_API_KEY is missing, collector must return empty list without crashing or falling back to fake data."""
    collector = RedditCollector(api_key="", use_tavily=True)
    results = collector.collect(sample_niche, use_cache=False)
    assert results == []
    assert isinstance(results, list)

    with patch("src.collectors.reddit.settings.tavily_api_key", ""):
        collector_no_key = RedditCollector(api_key=None, use_tavily=True)
        assert collector_no_key.collect(sample_niche, use_cache=False) == []


@patch("tavily.TavilyClient")
def test_two_queries_per_niche_with_default_budget(mock_tavily_cls, sample_niche):
    """With default budget knobs (max_seeds=1, max_intents=2, max_queries_per_intent=1),
    exactly two Tavily search calls must be made per niche (pain + regret intents),
    regardless of how many seed keywords the niche has."""
    mock_client = MagicMock()
    mock_tavily_cls.return_value = mock_client
    mock_client.search.return_value = {"results": []}

    niche_with_many_seeds = Niche(
        id="multi_seed",
        name="Multi seed niche",
        seed_keywords=["seed one", "seed two", "seed three"],
    )

    collector = RedditCollector(api_key="tvly-mock-key", use_tavily=True)
    collector.collect(niche_with_many_seeds, use_cache=False)

    assert mock_client.search.call_count == 2


@patch("tavily.TavilyClient")
def test_regret_intent_included_with_default_budget(mock_tavily_cls, sample_niche):
    """The regret intent ("waste of money" / "regret buying") must be queried
    alongside pain by default — it's the clearest signal of product risk, and was
    previously never collected because max_intents defaulted to 1."""
    mock_client = MagicMock()
    mock_tavily_cls.return_value = mock_client
    mock_client.search.return_value = {"results": []}

    collector = RedditCollector(api_key="tvly-mock-key", use_tavily=True)
    collector.collect(sample_niche, use_cache=False)

    queries = [call.kwargs["query"] for call in mock_client.search.call_args_list]
    assert any("waste of money" in q for q in queries)
    assert any("hard to choose" in q for q in queries)


def test_strip_boilerplate_removes_navigation_junk():
    """Patterns copied verbatim from real Tavily responses (data/raw/reddit_*.json)
    must be stripped, while the genuine post content survives intact."""
    from src.collectors.reddit import _strip_boilerplate

    raw = (
        "Skip to main contentChristmas Gift Ideas for hard to shop for dad? "
        "Open menu Open navigationGo to Reddit Home. Get App Get the Reddit app "
        "Log InLog in to Reddit. Expand user menu Open settings menu. "
        "So, my dad is near impossible to get gifts for. He likes heavy metal music."
    )
    cleaned = _strip_boilerplate(raw)

    assert "skip to main content" not in cleaned.lower()
    assert "open menu" not in cleaned.lower()
    assert "go to reddit home" not in cleaned.lower()
    assert "log in to reddit" not in cleaned.lower()
    assert "expand user menu" not in cleaned.lower()
    assert "So, my dad is near impossible to get gifts for. He likes heavy metal music." in cleaned


def test_strip_boilerplate_removes_reply_thread_artifacts():
    """Comment-thread chrome ("3 more replies", "[deleted]", "•9mo ago") must not be
    mistaken for genuine customer testimony."""
    from src.collectors.reddit import _strip_boilerplate

    raw = (
        "Fine jewelry in her style is a great gift. [deleted]\n\n•9mo ago\n\n"
        "3 more replies \n\n1 more reply"
    )
    cleaned = _strip_boilerplate(raw)

    assert "[deleted]" not in cleaned
    assert "more repl" not in cleaned.lower()
    assert "mo ago" not in cleaned.lower()
    assert "Fine jewelry in her style is a great gift." in cleaned


@patch("tavily.TavilyClient")
def test_boilerplate_stripping_applied_before_length_filter(mock_tavily_cls, sample_niche):
    """A result that is only >=40 chars because of navigation junk must still be
    dropped once that junk is stripped — the length filter must run on cleaned text,
    not raw Tavily content."""
    mock_client = MagicMock()
    mock_tavily_cls.return_value = mock_client
    mock_client.search.return_value = {
        "results": [
            {
                "title": "Mostly chrome, barely any content",
                "url": "https://www.reddit.com/r/gifts/comments/junkonly/test/",
                "content": "Skip to main content Open menu Open navigation Go to Reddit Home. OK.",
            }
        ]
    }

    collector = RedditCollector(api_key="tvly-mock-key", use_tavily=True)
    results = collector.collect(sample_niche, use_cache=False)

    assert len(results) == 0


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

    collector = RedditCollector(api_key="tvly-mock-key", use_tavily=True)
    results = collector.collect(sample_niche, use_cache=False)

    post_ids = [item.post_id for item in results]
    assert len(post_ids) == 1
    assert post_ids[0] == "dup123"


@patch("tavily.TavilyClient")
def test_resilience_to_single_query_failure(mock_tavily_cls, sample_niche):
    """A failure in one query must not crash the entire collector."""
    mock_client = MagicMock()
    mock_tavily_cls.return_value = mock_client
    mock_client.search.side_effect = RuntimeError("Temporary network timeout")

    collector = RedditCollector(api_key="tvly-mock-key", use_tavily=True)
    collector.backoff_base = 0.01  # Speed up test retries
    results = collector.collect(sample_niche, use_cache=False)

    assert isinstance(results, list)
    assert results == []


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

    collector = RedditCollector(api_key="tvly-mock-key", use_tavily=True)
    results = collector.collect(sample_niche, use_cache=False)

    assert len(results) > 0
    for r in results:
        # Check absence of fabricated strings
        assert "Thảo luận cộng đồng" not in r.text
        assert "Insight:" not in r.text
        assert r.value is None
        assert "upvote" not in (r.text.lower())
        assert r.intent == "pain"  # first intent in config (max_intents=1)
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

    collector = RedditCollector(api_key="tvly-mock-key", use_tavily=True)
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

    collector = RedditCollector(api_key="tvly-mock-key", use_tavily=True)
    results = collector.collect(sample_niche, use_cache=False)
    assert len(results) == 0


@patch("tavily.TavilyClient")
def test_writes_cache_even_when_use_cache_false(mock_tavily_cls, sample_niche):
    """use_cache=False must only skip the cache *read*, not the write — matching
    google_suggest/web_search/serpapi_trends, which always persist raw results so
    data/raw/ stays inspectable regardless of the cache toggle. This was the root
    cause of Reddit producing zero cache files while every other collector wrote
    theirs during a --no-cache run."""
    mock_client = MagicMock()
    mock_tavily_cls.return_value = mock_client
    mock_client.search.return_value = {
        "results": [
            {
                "title": "No-cache write test",
                "url": "https://www.reddit.com/r/gifts/comments/nocache1/test/",
                "content": "This result must still be written to disk even though use_cache=False.",
                "score": 0.5,
            }
        ]
    }

    collector = RedditCollector(api_key="tvly-mock-key", use_tavily=True)
    collector.collect(sample_niche, use_cache=False)

    # Niche-level cache file must exist despite use_cache=False.
    cached = cache.get_raw(collector.name, sample_niche.name)
    assert cached is not None
    assert len(cached) == 1
    assert cached[0]["post_id"] == "nocache1"


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

    collector = RedditCollector(api_key="tvly-mock-key", use_tavily=True)
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
