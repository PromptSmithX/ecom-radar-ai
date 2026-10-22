"""Reddit community collector using Tavily API to extract authentic customer feedback and discussions."""

from __future__ import annotations
import hashlib
import inspect
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set
from src.core.cache import cache
from src.core.config import settings
from src.core.models import Evidence, Niche
from .base import Collector

logger = logging.getLogger(__name__)

# Regex strictly matching valid Reddit thread permalinks
# Excludes search pages, subreddit roots, user profiles
REDDIT_THREAD_PATTERN = re.compile(
    r"reddit\.com/r/([^/]+)/comments/([a-z0-9]+)/?",
    re.IGNORECASE,
)

DEFAULT_INTENTS: Dict[str, List[str]] = {
    "ask": [
        "looking for {seed}",
        "what should I get {seed}",
    ],
    "pain": [
        "{seed} hard to choose",
        "{seed} who has everything",
    ],
    "regret": [
        "{seed} waste of money",
        "regret buying {seed}",
    ],
    "recommend": [
        "best {seed} worth it",
        "{seed} actually use",
    ],
}


class RedditCollector(Collector):
    name: str = "reddit"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key if api_key is not None else settings.tavily_api_key
        reddit_cfg = settings.collectors.reddit

        self.max_results_per_query: int = getattr(reddit_cfg, "max_results_per_query", 5) or 5
        self.time_range: str = getattr(reddit_cfg, "time_range", "year") or "year"
        self.search_depth: str = getattr(reddit_cfg, "search_depth", "advanced") or "advanced"
        self.preferred_subreddits: List[str] = getattr(
            reddit_cfg,
            "preferred_subreddits",
            ["gifts", "GiftIdeas", "BuyItForLife", "AskMen", "AskWomen", "Etsy"],
        ) or ["gifts", "GiftIdeas", "BuyItForLife", "AskMen", "AskWomen", "Etsy"]

        configured_intents = getattr(reddit_cfg, "intents", None)
        self.intents: Dict[str, List[str]] = configured_intents if configured_intents else DEFAULT_INTENTS
        self.max_queries_per_intent: Optional[int] = getattr(reddit_cfg, "max_queries_per_intent", None)

        self.max_retries: int = 3
        self.backoff_base: float = 2.0

    def _get_supported_tavily_params(self, client: Any) -> Set[str]:
        """Inspects TavilyClient.search signature to safely pass only supported parameters."""
        try:
            sig = inspect.signature(client.search)
            return set(sig.parameters.keys())
        except Exception as e:
            logger.debug(f"Could not inspect TavilyClient.search signature: {e}")
            return {"query", "search_depth", "time_range", "max_results", "include_domains"}

    def _build_query_cache_key(self, query: str) -> str:
        """Constructs an identifier for query-level caching using core.cache."""
        clean_q = re.sub(r"[^\w\-_]", "_", query.lower()).strip("_")[:50]
        hash_suffix = hashlib.md5(f"{query}_{self.time_range}_{self.search_depth}".encode("utf-8")).hexdigest()[:8]
        return f"query_{clean_q}_{hash_suffix}"

    def _execute_search_with_retry(
        self,
        client: Any,
        query: str,
        supported_params: Set[str],
    ) -> List[Dict[str, Any]]:
        """Executes a single Tavily search call with rate-limit (429) backoff retry."""
        params: Dict[str, Any] = {
            "query": query,
            "include_domains": ["reddit.com"],
        }

        if "search_depth" in supported_params:
            params["search_depth"] = self.search_depth
        else:
            logger.warning("TavilyClient.search does not support 'search_depth'; skipping parameter.")

        if "time_range" in supported_params and self.time_range:
            params["time_range"] = self.time_range
        elif "time_range" not in supported_params and self.time_range:
            logger.warning("TavilyClient.search does not support 'time_range'; skipping parameter.")

        if "max_results" in supported_params:
            params["max_results"] = self.max_results_per_query

        for attempt in range(self.max_retries):
            try:
                response = client.search(**params)
                return response.get("results", []) or []
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "rate limit" in err_msg.lower():
                    sleep_seconds = self.backoff_base * (attempt + 1)
                    logger.warning(
                        f"Tavily rate limit (429) hit for query '{query}'. Retrying in {sleep_seconds}s "
                        f"(attempt {attempt + 1}/{self.max_retries})..."
                    )
                    time.sleep(sleep_seconds)
                else:
                    logger.warning(f"Tavily search error for query '{query}' (attempt {attempt + 1}): {e}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.backoff_base)
                    else:
                        logger.warning(f"Tavily search permanently failed for query '{query}': {e}")
                        return []
        return []

    def collect(
        self,
        niche: Niche,
        use_cache: bool = True,
        extra_terms: Optional[List[str]] = None,
    ) -> List[Evidence]:
        """Collects authentic Reddit discussion threads for the given niche.

        Args:
            niche: Target niche containing seed keywords.
            use_cache: Whether to read/write query cache.
            extra_terms: Optional long-tail or rising terms from previous collectors (TODO: hook into pipeline).

        Returns:
            List of genuine Evidence models linked directly to Reddit comment threads.
        """
        # 1. No API key configured: log warning and return empty list (no silent mock)
        if not self.api_key or not self.api_key.strip():
            logger.warning(
                f"TAVILY_API_KEY is not configured. RedditCollector returning empty evidence list for '{niche.name}'."
            )
            return []

        # 2. Check niche-level cache first if enabled
        if use_cache:
            cached_niche_data = cache.get_raw(self.name, niche.name)
            if cached_niche_data is not None:
                logger.info(f"Loaded Reddit evidence from niche cache for: {niche.name}")
                return [Evidence(**item) for item in cached_niche_data]

        # 3. Initialize Tavily client
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=self.api_key.strip())
            supported_params = self._get_supported_tavily_params(client)
        except Exception as e:
            logger.warning(f"Could not initialize TavilyClient: {e}. RedditCollector returning empty list.")
            return []

        # 3. Determine keywords to query
        # TODO: If pipeline supports passing previous evidence, supply up to 3 extra_terms here.
        seeds = list(niche.seed_keywords) if niche.seed_keywords else [niche.name]
        if extra_terms:
            seeds.extend(extra_terms[:3])

        seen_post_ids: Set[str] = set()
        evidence_list: List[Evidence] = []

        # 4. Query by intent
        for seed in seeds:
            for intent_name, templates in self.intents.items():
                selected_templates = (
                    templates[:self.max_queries_per_intent]
                    if self.max_queries_per_intent
                    else templates
                )

                for tmpl in selected_templates:
                    raw_q = tmpl.format(seed=seed).strip()
                    # Append " reddit" suffix for authentic Reddit phrasing without duplicating
                    query = f"{raw_q} reddit" if not raw_q.lower().endswith("reddit") else raw_q

                    cache_key = self._build_query_cache_key(query)
                    raw_results: Optional[List[Dict[str, Any]]] = None

                    # Check query-level cache
                    if use_cache:
                        raw_results = cache.get_raw(self.name, cache_key)
                        if raw_results is not None:
                            logger.debug(f"Loaded {len(raw_results)} cached Tavily results for query: '{query}'")

                    if raw_results is None:
                        logger.info(f"Querying Tavily [intent={intent_name}]: '{query}'")
                        raw_results = self._execute_search_with_retry(client, query, supported_params)
                        if raw_results is not None and use_cache:
                            cache.set_raw(self.name, cache_key, raw_results)

                    # 5. Filter and deduplicate
                    for r in raw_results or []:
                        url = r.get("url") or ""
                        match = REDDIT_THREAD_PATTERN.search(url)
                        if not match:
                            # Discard search pages, subreddit roots, user profiles
                            continue

                        subreddit = match.group(1)
                        post_id = match.group(2).lower()

                        if post_id in seen_post_ids:
                            continue

                        title = (r.get("title") or "").strip()
                        if not title:
                            continue

                        # Extract exact verbatim snippet from Tavily content, truncated to max 500 chars
                        content = (r.get("content") or "").strip()
                        snippet = content[:500].strip()
                        if len(snippet) < 40:
                            # Drop records with too short snippets
                            continue

                        seen_post_ids.add(post_id)

                        # Extract relevance score (never call it upvotes)
                        score_val = r.get("score")
                        relevance: Optional[float] = None
                        if score_val is not None:
                            try:
                                relevance = float(score_val)
                            except (ValueError, TypeError):
                                relevance = None

                        # Retain canonical thread URL
                        canonical_url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/"

                        ev = Evidence(
                            source=self.name,
                            intent=intent_name,
                            subreddit=subreddit,
                            post_id=post_id,
                            title=title,
                            snippet=snippet,
                            relevance=relevance,
                            keyword=seed,
                            source_url=canonical_url,
                            query_used=query,
                            text=snippet,
                            value=None,  # No fabricated upvotes or metrics
                            kind="complaint",  # Compatible with downstream pipeline
                            is_mock=False,
                        )
                        evidence_list.append(ev)

        # 6. Prioritize preferred subreddits
        pref_lower = {s.lower() for s in self.preferred_subreddits}
        evidence_list.sort(
            key=lambda item: 0 if (item.subreddit and item.subreddit.lower() in pref_lower) else 1
        )

        # 7. Lưu cache dữ liệu thô cấp Niche (data/raw/reddit_{niche_name}.json) đồng bộ với các collector khác
        if evidence_list and use_cache:
            cache.set_raw(self.name, niche.name, [item.model_dump() for item in evidence_list])

        logger.info(
            f"RedditCollector finished for niche '{niche.name}': {len(evidence_list)} genuine thread records collected."
        )
        return evidence_list
