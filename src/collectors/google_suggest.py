"""Google Suggest / Autocomplete collector, with DuckDuckGo and Bing as fallbacks.

Google's suggest endpoint rate-limits (429) an IP after repeated runs. DuckDuckGo
and Bing expose the same ["query", [suggestions...]] autocomplete shape, so they
act as drop-in backups tried in order — whichever answers first is used, and the
evidence text always names the provider that actually produced it.
"""

from __future__ import annotations
import logging
import time
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Tuple
import httpx
from src.core.cache import cache
from src.core.config import settings
from src.core.models import Evidence, Niche
from .base import Collector

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

ProviderBuilder = Callable[[str, str, str], Tuple[str, Dict[str, Any]]]


def _build_google_params(query: str, client_param: str, hl: str) -> Tuple[str, Dict[str, Any]]:
    return (
        "https://suggestqueries.google.com/complete/search",
        {"client": client_param, "hl": hl, "q": query},
    )


def _build_duckduckgo_params(query: str, client_param: str, hl: str) -> Tuple[str, Dict[str, Any]]:
    return ("https://duckduckgo.com/ac/", {"type": "list", "q": query})


def _build_bing_params(query: str, client_param: str, hl: str) -> Tuple[str, Dict[str, Any]]:
    return ("https://api.bing.com/osjson.aspx", {"query": query})


PROVIDER_BUILDERS: Dict[str, ProviderBuilder] = {
    "google": _build_google_params,
    "duckduckgo": _build_duckduckgo_params,
    "bing": _build_bing_params,
}

PROVIDER_DISPLAY_NAMES: Dict[str, str] = {
    "google": "Google Autocomplete",
    "duckduckgo": "DuckDuckGo Autocomplete",
    "bing": "Bing Autocomplete",
}


class GoogleSuggestCollector(Collector):
    name: str = "google_suggest"

    def __init__(self):
        cfg = settings.collectors.google_suggest
        self.client_param = cfg.client
        self.hl = cfg.hl
        self.providers: List[str] = getattr(cfg, "providers", None) or ["google", "duckduckgo", "bing"]
        self.request_delay: float = getattr(cfg, "request_delay", 1.0) or 1.0
        self.max_suggestions: int = getattr(cfg, "max_suggestions", 6) or 6

    def _query_provider(self, client: httpx.Client, provider: str, seed: str) -> Optional[List[str]]:
        """Queries a single autocomplete provider. Returns suggestions or None on failure."""
        builder = PROVIDER_BUILDERS.get(provider)
        if builder is None:
            logger.warning(f"Unknown Google Suggest provider '{provider}'; skipping.")
            return None

        url, params = builder(seed, self.client_param, self.hl)
        try:
            resp = client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning(f"{PROVIDER_DISPLAY_NAMES.get(provider, provider)} returned {resp.status_code} for '{seed}'.")
                return None
            data = resp.json()
            suggestions = data[1] if len(data) > 1 and isinstance(data[1], list) else []
            if not suggestions:
                return None
            return [str(s) for s in suggestions if s]
        except Exception as e:
            logger.warning(f"{PROVIDER_DISPLAY_NAMES.get(provider, provider)} query failed for '{seed}': {e}")
            return None

    def collect(self, niche: Niche, use_cache: bool = True) -> List[Evidence]:
        evidence_list: List[Evidence] = []
        if use_cache:
            cached_data = cache.get_raw(self.name, niche.name)
            if cached_data is not None:
                for item in cached_data:
                    evidence_list.append(Evidence(**item))
                return evidence_list

        raw_results = []
        headers = {"User-Agent": USER_AGENT}

        with httpx.Client(timeout=10.0, headers=headers) as client:
            for seed in niche.seed_keywords:
                suggestions: Optional[List[str]] = None
                used_provider = "google"

                for provider in self.providers:
                    suggestions = self._query_provider(client, provider, seed)
                    if suggestions:
                        used_provider = provider
                        break
                    time.sleep(self.request_delay)

                if not suggestions:
                    logger.warning(f"All Google Suggest providers failed for seed '{seed}'; skipping.")
                    continue

                provider_name = PROVIDER_DISPLAY_NAMES.get(used_provider, used_provider)
                top_suggestions = suggestions[: self.max_suggestions]
                for idx, sug in enumerate(top_suggestions):
                    if not sug:
                        continue
                    rank = idx + 1
                    encoded_q = urllib.parse.quote_plus(sug)
                    ev = Evidence(
                        source=self.name,
                        kind="keyword_signal",
                        keyword=sug,
                        text=f"{provider_name} gợi ý #{rank}/{len(top_suggestions)} khi tìm '{seed}': '{sug}' (không kèm số liệu định lượng)",
                        value=f"Vị trí gợi ý #{rank} trong Autocomplete",
                        source_url=f"https://trends.google.com/trends/explore?q={encoded_q}&date=today%203-m",
                    )
                    evidence_list.append(ev)
                    raw_results.append(ev.model_dump())

                time.sleep(self.request_delay)

        if raw_results:
            cache.set_raw(self.name, niche.name, raw_results)

        return evidence_list
