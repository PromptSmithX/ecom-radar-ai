"""Google Suggest / Autocomplete collector."""

from __future__ import annotations
import urllib.parse
from typing import List
import httpx
from src.core.cache import cache
from src.core.config import settings
from src.core.models import Evidence, Niche
from .base import Collector


class GoogleSuggestCollector(Collector):
    name: str = "google_suggest"

    def __init__(self):
        self.endpoint = "https://suggestqueries.google.com/complete/search"
        self.client_param = settings.collectors.google_suggest.client
        self.hl = settings.collectors.google_suggest.hl

    def collect(self, niche: Niche) -> List[Evidence]:
        evidence_list: List[Evidence] = []
        cached_data = cache.get_raw(self.name, niche.name)
        if cached_data is not None:
            for item in cached_data:
                evidence_list.append(Evidence(**item))
            return evidence_list

        raw_results = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        with httpx.Client(timeout=10.0, headers=headers) as client:
            for seed in niche.seed_keywords:
                try:
                    params = {
                        "client": self.client_param,
                        "hl": self.hl,
                        "q": seed,
                    }
                    resp = client.get(self.endpoint, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        # data structure: [query, [suggestions...]]
                        suggestions = data[1] if len(data) > 1 and isinstance(data[1], list) else []
                        for sug in suggestions[:6]:
                            if not sug:
                                continue
                            encoded_q = urllib.parse.quote_plus(sug)
                            ev = Evidence(
                                source=self.name,
                                kind="keyword_signal",
                                keyword=sug,
                                text=f"Google Autocomplete gợi ý tìm kiếm xu hướng: '{sug}' từ seed keyword '{seed}'",
                                value="Top Google Autocomplete Suggestion",
                                source_url=f"https://www.google.com/search?q={encoded_q}",
                            )
                            evidence_list.append(ev)
                            raw_results.append(ev.model_dump())
                except Exception as e:
                    # Soft failure per seed keyword
                    continue

        if raw_results:
            cache.set_raw(self.name, niche.name, raw_results)

        return evidence_list
