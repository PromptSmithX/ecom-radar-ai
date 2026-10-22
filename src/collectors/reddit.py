"""Reddit community collector using public JSON endpoint (default) and optional Tavily API."""

from __future__ import annotations
import hashlib
import inspect
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set
import httpx
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

REDDIT_SEARCH_URL = "https://www.reddit.com/search.json"


class RedditCollector(Collector):
    name: str = "reddit"

    def __init__(self, api_key: Optional[str] = None, use_tavily: Optional[bool] = None):
        self.api_key = api_key if api_key is not None else settings.tavily_api_key
        reddit_cfg = settings.collectors.reddit

        # Tavily toggle: explicit arg > config > default False
        self.use_tavily = use_tavily if use_tavily is not None else getattr(reddit_cfg, "use_tavily", False)

        # Reddit JSON public endpoint settings
        self.request_delay: float = getattr(reddit_cfg, "request_delay", 3.0) or 3.0
        self.limit: int = getattr(reddit_cfg, "limit", 10) or 10
        self.sort: str = getattr(reddit_cfg, "sort", "relevance") or "relevance"
        self.time_filter: str = getattr(reddit_cfg, "time_filter", "month") or "month"

        # Tavily settings
        self.max_results_per_query: int = getattr(reddit_cfg, "max_results_per_query", 5) or 5
        self.time_range: str = getattr(reddit_cfg, "time_range", "year") or "year"
        self.search_depth: str = getattr(reddit_cfg, "search_depth", "basic") or "basic"
        self.preferred_subreddits: List[str] = getattr(
            reddit_cfg,
            "preferred_subreddits",
            ["gifts", "GiftIdeas", "BuyItForLife", "AskMen", "AskWomen", "Etsy"],
        ) or ["gifts", "GiftIdeas", "BuyItForLife", "AskMen", "AskWomen", "Etsy"]

        configured_intents = getattr(reddit_cfg, "intents", None)
        self.intents: Dict[str, List[str]] = configured_intents if configured_intents else DEFAULT_INTENTS
        self.max_queries_per_intent: int = getattr(reddit_cfg, "max_queries_per_intent", 1) or 1

        self.max_retries: int = 3
        self.backoff_base: float = 2.0

    # ----------------------------------------------------------------
    # Backend: Reddit public JSON endpoint (no API key required)
    # ----------------------------------------------------------------
    def _search_reddit_json(self, query: str) -> List[Dict[str, Any]]:
        """Searches Reddit via the public search.json endpoint. Returns normalized results."""
        params = {
            "q": query,
            "sort": self.sort,
            "t": self.time_filter,
            "limit": self.limit,
            "type": "link",
            "restrict_sr": "",
        }
        headers = {"User-Agent": settings.reddit_user_agent}

        for attempt in range(self.max_retries):
            try:
                resp = httpx.get(REDDIT_SEARCH_URL, params=params, headers=headers, timeout=15)
                if resp.status_code == 429 or resp.status_code == 403:
                    sleep_seconds = self.backoff_base * (attempt + 1)
                    logger.warning(
                        f"Reddit JSON {resp.status_code} for query '{query}'. "
                        f"Retrying in {sleep_seconds}s (attempt {attempt + 1}/{self.max_retries})..."
                    )
                    time.sleep(sleep_seconds)
                    continue
                resp.raise_for_status()

                data = resp.json()
                children = data.get("data", {}).get("children", [])
                results = []
                for child in children:
                    post = child.get("data", {})
                    permalink = post.get("permalink", "")
                    if not permalink:
                        continue
                    title = (post.get("title") or "").strip()
                    selftext = (post.get("selftext") or "").strip()
                    score = post.get("score")
                    subreddit = post.get("subreddit", "")

                    results.append({
                        "url": f"https://www.reddit.com{permalink}",
                        "title": title,
                        "content": selftext if selftext else title,
                        "score": score,
                        "subreddit": subreddit,
                    })

                # Throttle to avoid rate limits
                time.sleep(self.request_delay)
                return results

            except httpx.HTTPStatusError as e:
                logger.warning(f"Reddit JSON HTTP error for query '{query}' (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff_base)
                else:
                    logger.warning(f"Reddit JSON permanently failed for query '{query}': {e}")
                    return []
            except Exception as e:
                logger.warning(f"Reddit JSON error for query '{query}' (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff_base)
                else:
                    logger.warning(f"Reddit JSON permanently failed for query '{query}': {e}")
                    return []
        return []

    # ----------------------------------------------------------------
    # Backend: Tavily API (optional, only when use_tavily=True)
    # ----------------------------------------------------------------
    def _get_supported_tavily_params(self, client: Any) -> Set[str]:
        """Inspects TavilyClient.search signature to safely pass only supported parameters."""
        try:
            sig = inspect.signature(client.search)
            return set(sig.parameters.keys())
        except Exception as e:
            logger.debug(f"Could not inspect TavilyClient.search signature: {e}")
            return {"query", "search_depth", "time_range", "max_results", "include_domains"}

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

    # ----------------------------------------------------------------
    # Cache helpers
    # ----------------------------------------------------------------
    def _build_query_cache_key(self, query: str, backend: str = "json") -> str:
        """Constructs an identifier for query-level caching, namespaced by backend."""
        clean_q = re.sub(r"[^\w\-_]", "_", query.lower()).strip("_")[:50]
        hash_suffix = hashlib.md5(f"{query}_{self.time_range}_{self.search_depth}_{backend}".encode("utf-8")).hexdigest()[:8]
        return f"{backend}_query_{clean_q}_{hash_suffix}"

    def _niche_cache_key(self, niche_name: str, backend: str = "json") -> str:
        """Returns backend-specific niche cache key."""
        return f"{backend}_{niche_name}"

    # ----------------------------------------------------------------
    # Main collect method
    # ----------------------------------------------------------------
    def collect(
        self,
        niche: Niche,
        use_cache: bool = True,
        extra_terms: Optional[List[str]] = None,
    ) -> List[Evidence]:
        """Collects authentic Reddit discussion threads for the given niche.

        Uses the public Reddit JSON endpoint by default.
        Optionally supplements with Tavily results when use_tavily=True.
        """
        # 1. Check niche-level cache for JSON backend
        if use_cache:
            json_cache_key = self._niche_cache_key(niche.name, "json")
            cached_json = cache.get_raw(self.name, json_cache_key)
            if cached_json is not None:
                logger.info(f"Loaded Reddit JSON evidence from niche cache for: {niche.name}")
                evidence_from_cache = [Evidence(**item) for item in cached_json]

                # If Tavily is enabled, also check Tavily cache
                if self.use_tavily and self.api_key and self.api_key.strip():
                    tavily_cache_key = self._niche_cache_key(niche.name, "tavily")
                    cached_tavily = cache.get_raw(self.name, tavily_cache_key)
                    if cached_tavily is not None:
                        logger.info(f"Loaded Reddit Tavily evidence from niche cache for: {niche.name}")
                        # Dedupe by post_id
                        seen_ids = {e.post_id for e in evidence_from_cache if e.post_id}
                        for item in cached_tavily:
                            ev = Evidence(**item)
                            if ev.post_id and ev.post_id not in seen_ids:
                                evidence_from_cache.append(ev)
                                seen_ids.add(ev.post_id)
                return evidence_from_cache

        # 2. Determine keywords to query
        seeds = list(niche.seed_keywords) if niche.seed_keywords else [niche.name]
        if extra_terms:
            seeds.extend(extra_terms[:3])

        seen_post_ids: Set[str] = set()
        json_evidence: List[Evidence] = []
        tavily_evidence: List[Evidence] = []

        # 3. Initialize Tavily client if enabled
        tavily_client = None
        tavily_supported_params: Set[str] = set()
        if self.use_tavily and self.api_key and self.api_key.strip():
            try:
                from tavily import TavilyClient
                tavily_client = TavilyClient(api_key=self.api_key.strip())
                tavily_supported_params = self._get_supported_tavily_params(tavily_client)
            except Exception as e:
                logger.warning(f"Could not initialize TavilyClient: {e}. Tavily supplement disabled.")

        # 4. Query by intent — JSON backend (always runs)
        for seed in seeds:
            for intent_name, templates in self.intents.items():
                selected_templates = templates[:self.max_queries_per_intent]

                for tmpl in selected_templates:
                    raw_q = tmpl.format(seed=seed).strip()
                    query = f"{raw_q} reddit" if not raw_q.lower().endswith("reddit") else raw_q

                    # --- JSON backend ---
                    json_cache_key = self._build_query_cache_key(query, "json")
                    raw_results: Optional[List[Dict[str, Any]]] = None

                    if use_cache:
                        raw_results = cache.get_raw(self.name, json_cache_key)
                        if raw_results is not None:
                            logger.debug(f"Loaded {len(raw_results)} cached JSON results for query: '{query}'")

                    if raw_results is None:
                        logger.info(f"Querying Reddit JSON [intent={intent_name}]: '{query}'")
                        raw_results = self._search_reddit_json(query)
                        if raw_results is not None and use_cache:
                            cache.set_raw(self.name, json_cache_key, raw_results)

                    self._process_results(raw_results, seed, intent_name, query, seen_post_ids, json_evidence)

                    # --- Tavily backend (optional) ---
                    if tavily_client is not None:
                        tavily_cache_key = self._build_query_cache_key(query, "tavily")
                        tavily_results: Optional[List[Dict[str, Any]]] = None

                        if use_cache:
                            tavily_results = cache.get_raw(self.name, tavily_cache_key)
                            if tavily_results is not None:
                                logger.debug(f"Loaded {len(tavily_results)} cached Tavily results for query: '{query}'")

                        if tavily_results is None:
                            logger.info(f"Querying Tavily [intent={intent_name}]: '{query}'")
                            tavily_results = self._execute_search_with_retry(tavily_client, query, tavily_supported_params)
                            if tavily_results is not None and use_cache:
                                cache.set_raw(self.name, tavily_cache_key, tavily_results)

                        self._process_results(tavily_results, seed, intent_name, query, seen_post_ids, tavily_evidence)

        # 5. Merge results: JSON first, then Tavily supplements
        all_evidence = json_evidence + tavily_evidence

        # 6. Prioritize preferred subreddits
        pref_lower = {s.lower() for s in self.preferred_subreddits}
        all_evidence.sort(
            key=lambda item: 0 if (item.subreddit and item.subreddit.lower() in pref_lower) else 1
        )

        # 7. Save niche-level cache per backend
        if use_cache:
            if json_evidence:
                cache.set_raw(self.name, self._niche_cache_key(niche.name, "json"),
                              [item.model_dump() for item in json_evidence])
            if tavily_evidence:
                cache.set_raw(self.name, self._niche_cache_key(niche.name, "tavily"),
                              [item.model_dump() for item in tavily_evidence])

        logger.info(
            f"RedditCollector finished for niche '{niche.name}': "
            f"{len(json_evidence)} JSON + {len(tavily_evidence)} Tavily = {len(all_evidence)} total records."
        )
        return all_evidence

    def _process_results(
        self,
        raw_results: Optional[List[Dict[str, Any]]],
        seed: str,
        intent_name: str,
        query: str,
        seen_post_ids: Set[str],
        evidence_list: List[Evidence],
    ) -> None:
        """Filters, deduplicates, and converts raw search results to Evidence objects."""
        for r in raw_results or []:
            url = r.get("url") or ""
            match = REDDIT_THREAD_PATTERN.search(url)
            if not match:
                continue

            subreddit = match.group(1)
            post_id = match.group(2).lower()

            if post_id in seen_post_ids:
                continue

            title = (r.get("title") or "").strip()
            if not title:
                continue

            content = (r.get("content") or "").strip()
            snippet = content[:500].strip()
            if len(snippet) < 40:
                continue

            seen_post_ids.add(post_id)

            score_val = r.get("score")
            relevance: Optional[float] = None
            if score_val is not None:
                try:
                    relevance = float(score_val)
                except (ValueError, TypeError):
                    relevance = None

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
                value=None,
                kind="complaint",
                is_mock=False,
            )
            evidence_list.append(ev)
