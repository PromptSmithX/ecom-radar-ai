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

    def collect(self, niche: Niche, use_cache: bool = True) -> List[Evidence]:
        evidence_list: List[Evidence] = []
        if use_cache:
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
                        top_suggestions = suggestions[:6]
                        for idx, sug in enumerate(top_suggestions):
                            if not sug:
                                continue
                            rank = idx + 1
                            encoded_q = urllib.parse.quote_plus(sug)
                            ev = Evidence(
                                source=self.name,
                                kind="keyword_signal",
                                keyword=sug,
                                text=f"Google Autocomplete gợi ý #{rank}/{len(top_suggestions)} khi tìm '{seed}': '{sug}' (không kèm số liệu định lượng)",
                                value=f"Vị trí gợi ý #{rank} trong Autocomplete",
                                source_url=f"https://trends.google.com/trends/explore?q={encoded_q}&date=today%203-m",
                            )
                            evidence_list.append(ev)
                            raw_results.append(ev.model_dump())
                except Exception as e:
                    # Soft failure per seed keyword
                    continue

        if raw_results:
            cache.set_raw(self.name, niche.name, raw_results)

        return evidence_list
