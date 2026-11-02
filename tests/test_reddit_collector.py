"""Unit tests for the new Reddit collector without Tavily dependency."""

from __future__ import annotations
from unittest.mock import MagicMock, patch
import pytest
from src.collectors.reddit import (
    COMMENT_PATTERN,
    REDDIT_THREAD_PATTERN,
    VOTE_PATTERN,
    RedditCollector,
    _parse_count_str,
)
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


def test_parse_count_str():
    """Tests parsing score and comment count numbers."""
    assert _parse_count_str("761") == 761
    assert _parse_count_str("49") == 49
    assert _parse_count_str("1.2k") == 1200
    assert _parse_count_str("25k") == 25000
    assert _parse_count_str("") is None
    assert _parse_count_str("none") is None


def test_vote_and_comment_regex():
    """Validates regex detection of votes and comments text."""
    vm = VOTE_PATTERN.search("761 votes · 49 comments")
    assert vm is not None
    assert "761" in vm.group(0)

    cm = COMMENT_PATTERN.search("761 votes · 49 comments")
    assert cm is not None
    assert "49" in cm.group(0)


def test_scrape_reddit_search_parses_html(sample_niche):
    """Tests DOM parsing of Reddit search results with mock BrowserManager."""
    mock_html = """
    <html><body>
    <div class="post-card">
      <a href="/r/gifts/comments/abc1234/great_christmas_ideas_for_mom/">Great Christmas Ideas For Mom</a>
      <span>761 votes · 49 comments</span>
    </div>
    </body></html>
    """
    mock_browser = MagicMock()
    mock_browser.fetch_page_content.return_value = mock_html

    collector = RedditCollector(browser_manager=mock_browser)
    results = collector._scrape_reddit_search("gifts", "christmas gift ideas")

    assert len(results) == 1
    post = results[0]
    assert post["post_id"] == "abc1234"
    assert post["subreddit"] == "gifts"
    assert post["score"] == 761
    assert post["comment_count"] == 49
    assert post["source_url"] == "https://www.reddit.com/r/gifts/comments/abc1234/"


def test_collect_returns_authentic_evidence(sample_niche):
    """Tests collect() workflow and Evidence creation."""
    mock_browser = MagicMock()
    mock_browser.fetch_page_content.return_value = """
    <html><body>
    <div>
      <a href="/r/gifts/comments/post99/best_gift_ever/">Best Gift Ever</a>
      <span>150 votes · 20 comments</span>
    </div>
    </body></html>
    """
    collector = RedditCollector(browser_manager=mock_browser)
    evidence_list = collector.collect(sample_niche, use_cache=False)

    assert len(evidence_list) >= 1
    first = evidence_list[0]
    assert isinstance(first, Evidence)
    assert first.source == "reddit"
    assert "150 upvotes" in first.text or "150 upvotes" in (first.value or "")
    assert first.source_url == "https://www.reddit.com/r/gifts/comments/post99/"
