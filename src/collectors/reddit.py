"""Reddit community collector using Playwright and DuckDuckGo fallback.

Collects authentic customer discussions, pain points, complaints, and recommendations
from targeted subreddits (r/gifts, r/GiftIdeas, r/BuyItForLife, etc.).
Extracts REAL upvote counts, comments counts, and post snippets without any fake numbers.
100% Free, no Reddit API key or Tavily API key required.
"""

from __future__ import annotations
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Set
from bs4 import BeautifulSoup
from ddgs import DDGS
from src.core.browser import BrowserManager
from src.core.cache import cache
from src.core.config import settings
from src.core.models import Evidence, Niche
from .base import Collector

logger = logging.getLogger(__name__)

REDDIT_THREAD_PATTERN = re.compile(
    r"https?://(?:www\.)?reddit\.com/r/([^/]+)/comments/([a-z0-9]+)/?([^\s\"'>]*)",
    re.IGNORECASE,
)

VOTE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:k\b)?\s*(?:votes?|upvotes?)", re.IGNORECASE)
COMMENT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:k\b)?\s*comments?", re.IGNORECASE)


def _parse_count_str(text: str) -> Optional[int]:
    """Parses numeric strings like '761', '1.2k' into integers."""
    if not text:
        return None
    cleaned = text.strip().lower()
    if "k" in cleaned:
        num_part = re.sub(r"[^\d.]", "", cleaned)
        try:
            return int(float(num_part) * 1000)
        except Exception:
            return None
    num_part = re.sub(r"[^\d]", "", cleaned)
    try:
        return int(num_part) if num_part else None
    except Exception:
        return None


class RedditCollector(Collector):
    name: str = "reddit"

    def __init__(self, browser_manager: Optional[BrowserManager] = None):
        reddit_cfg = settings.collectors.reddit
        self.preferred_subreddits: List[str] = getattr(
            reddit_cfg,
            "preferred_subreddits",
            ["gifts", "GiftIdeas", "BuyItForLife", "AskMen", "AskWomen", "Etsy"],
        ) or ["gifts", "GiftIdeas", "BuyItForLife", "AskMen", "AskWomen", "Etsy"]
        self.max_results: int = getattr(reddit_cfg, "max_results_per_query", 10) or 10
        self.browser_manager = browser_manager or BrowserManager.get_instance()

    def _scrape_reddit_search(self, subreddit: str, query: str) -> List[Dict[str, Any]]:
        """Scrapes reddit search page via Playwright."""
        url = f"https://www.reddit.com/r/{subreddit}/search/?q={urllib.parse.quote_plus(query)}&sort=top&t=year"
        posts: List[Dict[str, Any]] = []

        try:
            html = self.browser_manager.fetch_page_content(
                url,
                wait_selector="a[href*='/comments/']",
                delay_seconds=2.0,
            )
            soup = BeautifulSoup(html, "html.parser")

            # Look for comment links
            seen_permalinks = set()
            comment_links = soup.find_all("a", href=re.compile(r"/r/[^/]+/comments/([a-z0-9]+)/", re.IGNORECASE))

            for link in comment_links:
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = f"https://www.reddit.com{href}"

                # Normalize href to avoid query params
                match = REDDIT_THREAD_PATTERN.search(href)
                if not match:
                    continue
                sub_name = match.group(1)
                post_id = match.group(2)
                canonical_url = f"https://www.reddit.com/r/{sub_name}/comments/{post_id}/"

                if canonical_url in seen_permalinks:
                    continue
                seen_permalinks.add(canonical_url)

                title_text = link.get_text(strip=True)
                # Find parent container for votes and comments
                parent = link.find_parent(["div", "article", "li"])
                parent_text = parent.get_text(" ", strip=True) if parent else title_text

                # Parse score / votes
                score = None
                vm = VOTE_PATTERN.search(parent_text)
                if vm:
                    score = _parse_count_str(vm.group(0))

                # Parse comment count
                comment_count = None
                cm = COMMENT_PATTERN.search(parent_text)
                if cm:
                    comment_count = _parse_count_str(cm.group(0))

                if not title_text and parent:
                    # Look for h2 or h3 in parent
                    h = parent.find(["h2", "h3", "a"])
                    if h:
                        title_text = h.get_text(strip=True)

                if title_text:
                    posts.append({
                        "post_id": post_id,
                        "subreddit": sub_name,
                        "title": title_text,
                        "source_url": canonical_url,
                        "score": score,
                        "comment_count": comment_count,
                        "snippet": parent_text[:400] if parent_text else title_text,
                    })

                if len(posts) >= self.max_results:
                    break

        except Exception as e:
            logger.warning(f"Error scraping Reddit search for r/{subreddit} query '{query}': {e}")

        return posts

    def _fallback_ddg_reddit_search(self, query: str) -> List[Dict[str, Any]]:
        """Fallback to DuckDuckGo search if Reddit direct search returns few results."""
        posts: List[Dict[str, Any]] = []
        ddg_query = f"site:reddit.com/r/gifts OR site:reddit.com/r/GiftIdeas {query}"
        try:
            results = list(DDGS().text(ddg_query, max_results=self.max_results))
            for r in results:
                href = r.get("href", "")
                m = REDDIT_THREAD_PATTERN.search(href)
                if m:
                    sub_name = m.group(1)
                    post_id = m.group(2)
                    canonical_url = f"https://www.reddit.com/r/{sub_name}/comments/{post_id}/"
                    posts.append({
                        "post_id": post_id,
                        "subreddit": sub_name,
                        "title": r.get("title", ""),
                        "source_url": canonical_url,
                        "score": None,
                        "comment_count": None,
                        "snippet": r.get("body", ""),
                    })
        except Exception as e:
            logger.warning(f"DDG fallback for Reddit query '{query}' failed: {e}")
        return posts

    def collect(self, niche: Niche, use_cache: bool = True) -> List[Evidence]:
        if use_cache:
            cached_data = cache.get_raw(self.name, niche.name)
            if cached_data is not None:
                logger.info(f"Loaded Reddit evidence from cache for niche: {niche.name}")
                return [Evidence(**item) for item in cached_data]

        seeds = niche.seed_keywords if niche.seed_keywords else [niche.name]
        all_posts: List[Dict[str, Any]] = []
        seen_urls: Set[str] = set()

        for seed in seeds[:2]:
            # 1. Scrape Reddit directly with Playwright
            for sub in self.preferred_subreddits[:2]:
                items = self._scrape_reddit_search(sub, seed)
                for item in items:
                    if item["source_url"] not in seen_urls:
                        seen_urls.add(item["source_url"])
                        all_posts.append(item)

            # 2. If needed, supplement with DuckDuckGo
            if len(all_posts) < 3:
                ddg_items = self._fallback_ddg_reddit_search(seed)
                for item in ddg_items:
                    if item["source_url"] not in seen_urls:
                        seen_urls.add(item["source_url"])
                        all_posts.append(item)

        # Convert to Evidence objects
        evidence_list: List[Evidence] = []
        for post in all_posts[: self.max_results]:
            score_text = f"{post['score']} upvotes" if post.get("score") is not None else None
            comment_text = f"{post['comment_count']} comments" if post.get("comment_count") is not None else None
            metrics_summary = ", ".join(filter(None, [score_text, comment_text]))

            # Categorize kind based on title keywords
            lower_title = post["title"].lower()
            if any(w in lower_title for w in ["best", "recommend", "worth it", "favorite", "love"]):
                kind = "recommendation"
            elif any(w in lower_title for w in ["hard", "hate", "struggle", "annoying", "waste", "problem"]):
                kind = "complaint"
            elif any(w in lower_title for w in ["what", "help", "looking for", "idea", "suggestion"]):
                kind = "question"
            else:
                kind = "complaint"

            evidence_text = f"Thảo luận Reddit [r/{post['subreddit']}]: '{post['title']}'."
            if metrics_summary:
                evidence_text += f" ({metrics_summary})"
            if post.get("snippet"):
                evidence_text += f" — {post['snippet'][:250]}"

            ev = Evidence(
                source=self.name,
                kind=kind,
                keyword=niche.name,
                text=evidence_text,
                value=metrics_summary or "Thảo luận cộng đồng thực tế",
                source_url=post["source_url"],
                subreddit=post["subreddit"],
                post_id=post["post_id"],
                title=post["title"],
                snippet=post.get("snippet"),
            )
            evidence_list.append(ev)

        # Cache raw evidence
        cache.set_raw(self.name, niche.name, [e.model_dump() for e in evidence_list])
        logger.info(f"RedditCollector collected {len(evidence_list)} authentic items for '{niche.name}'.")
        return evidence_list
