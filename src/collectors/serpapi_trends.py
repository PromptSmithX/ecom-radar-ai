"""Google Trends data via SerpApi (https://serpapi.com), used as a fallback for pytrends
when it hits 429. Same circuit-breaker pattern as GoogleTrendsCollector, but with its own
cache namespace and cooldown key so the two never collide."""

from __future__ import annotations
import logging
import urllib.parse
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import httpx
from src.core.cache import cache
from src.core.config import settings
from src.core.models import Evidence, Niche
from .base import Collector

logger = logging.getLogger(__name__)

COOLDOWN_META_KEY = "serpapi_trends_cooldown"
SERPAPI_ENDPOINT = "https://serpapi.com/search.json"


def _explore_url(keyword: str, date: str) -> str:
    """SerpApi serves real Google Trends data, so the verifiable source link is the
    actual Google Trends explore page for the same keyword/date range."""
    return f"https://trends.google.com/trends/explore?q={urllib.parse.quote_plus(keyword)}&date={urllib.parse.quote_plus(date)}"


class SerpApiTrendsCollector(Collector):
    name: str = "serpapi_trends"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key if api_key is not None else settings.serpapi_api_key
        cfg = settings.collectors.serpapi
        self.hl = cfg.hl
        self.geo = cfg.geo
        self.date = cfg.date
        self.cooldown_minutes = cfg.cooldown_minutes
        self.include_interest_over_time = cfg.include_interest_over_time

    def _baseline_fallback(self, niche: Niche) -> List[Evidence]:
        logger.warning(f"SerpApi Trends could not reach online data for '{niche.name}', inserting baseline fallback evidence.")
        evidence_list: List[Evidence] = []
        for seed in niche.seed_keywords:
            ev = Evidence(
                source=self.name,
                kind="keyword_signal",
                keyword=seed,
                text=f"[FALLBACK] Từ khóa '{seed}' — SerpApi Trends lỗi/hết quota, không có dữ liệu thật",
                value="Baseline seasonal keyword (fallback)",
                source_url=_explore_url(seed, self.date),
                is_mock=True,
            )
            evidence_list.append(ev)
        return evidence_list

    def _request(self, client: httpx.Client, params: Dict[str, Any]) -> Dict[str, Any]:
        resp = client.get(SERPAPI_ENDPOINT, params=params)
        if resp.status_code == 429:
            raise RuntimeError("429 Too Many Requests")
        data = resp.json()
        error = data.get("error")
        if error:
            raise RuntimeError(str(error))
        return data

    def collect(self, niche: Niche, use_cache: bool = True) -> List[Evidence]:
        # 1. Cache first
        if use_cache:
            cached_data = cache.get_raw(self.name, niche.name)
            if cached_data is not None:
                logger.info(f"Loaded SerpApi Trends data from cache for niche: {niche.name}")
                return [Evidence(**item) for item in cached_data]

        # 2. No API key configured: log warning and return empty list (no silent mock)
        if not self.api_key or not self.api_key.strip():
            logger.warning(
                f"SERPAPI_API_KEY is not configured. SerpApiTrendsCollector returning empty evidence list for '{niche.name}'."
            )
            return []

        # 3. Circuit breaker: skip real calls while a previous quota/rate-limit error is on cooldown.
        cooldown_meta = cache.get_meta(COOLDOWN_META_KEY)
        if cooldown_meta and cooldown_meta.get("limited_until"):
            try:
                limited_until = datetime.fromisoformat(cooldown_meta["limited_until"])
                if datetime.now() < limited_until:
                    logger.warning(
                        f"SerpApi Trends đang trong cooldown (hết lúc {limited_until.isoformat()}). "
                        f"Bỏ qua gọi API thật cho '{niche.name}'."
                    )
                    return self._baseline_fallback(niche)
            except (ValueError, TypeError):
                pass

        kw_list = niche.seed_keywords if niche.seed_keywords else [niche.name]
        evidence_list: List[Evidence] = []
        raw_results: List[Dict[str, Any]] = []
        rate_limited = False

        with httpx.Client(timeout=15.0) as client:
            for kw in kw_list:
                if rate_limited:
                    break
                try:
                    data = self._request(
                        client,
                        {
                            "engine": "google_trends",
                            "q": kw,
                            "data_type": "RELATED_QUERIES",
                            "hl": self.hl,
                            "geo": self.geo,
                            "date": self.date,
                            "api_key": self.api_key.strip(),
                        },
                    )
                except Exception as e:
                    err_msg = str(e)
                    logger.warning(f"SerpApi Trends query '{kw}' failed: {err_msg}")
                    if "429" in err_msg or "run out of searches" in err_msg.lower() or "quota" in err_msg.lower():
                        logger.warning("SerpApi Trends rate limit/quota reached. Switching to baseline trends and setting cooldown.")
                        rate_limited = True
                        limited_until = datetime.now() + timedelta(minutes=self.cooldown_minutes)
                        cache.set_meta(COOLDOWN_META_KEY, {"limited_until": limited_until.isoformat()})
                    continue

                related = data.get("related_queries", {}) or {}

                for q_text, val in self._iter_queries(related.get("rising")):
                    ev = Evidence(
                        source=self.name,
                        kind="keyword_signal",
                        keyword=q_text,
                        text=f"SerpApi/Google Trends Rising query cho '{kw}': '{q_text}' tăng trưởng +{val}%",
                        value=f"+{val}% breakout/rising",
                        source_url=_explore_url(q_text, self.date),
                    )
                    evidence_list.append(ev)
                    raw_results.append(ev.model_dump())

                for q_text, val in self._iter_queries(related.get("top")):
                    ev = Evidence(
                        source=self.name,
                        kind="keyword_signal",
                        keyword=q_text,
                        text=f"SerpApi/Google Trends Top query cho '{kw}': '{q_text}' đạt điểm mức độ quan tâm {val}/100",
                        value=f"{val}/100 interest",
                        source_url=_explore_url(q_text, self.date),
                    )
                    evidence_list.append(ev)
                    raw_results.append(ev.model_dump())

                if self.include_interest_over_time:
                    ev = self._fetch_interest_over_time(client, kw)
                    if ev is not None:
                        evidence_list.append(ev)
                        raw_results.append(ev.model_dump())

        if not evidence_list:
            evidence_list = self._baseline_fallback(niche)
            raw_results = [ev.model_dump() for ev in evidence_list]

        if raw_results:
            cache.set_raw(self.name, niche.name, raw_results)

        return evidence_list

    @staticmethod
    def _iter_queries(items: Optional[List[Dict[str, Any]]]):
        for row in (items or [])[:5]:
            q_text = str(row.get("query", "")).strip()
            val = row.get("extracted_value", row.get("value", ""))
            if q_text:
                yield q_text, val

    def _fetch_interest_over_time(self, client: httpx.Client, kw: str) -> Optional[Evidence]:
        try:
            data = self._request(
                client,
                {
                    "engine": "google_trends",
                    "q": kw,
                    "data_type": "TIMESERIES",
                    "hl": self.hl,
                    "geo": self.geo,
                    "date": self.date,
                    "api_key": self.api_key.strip(),
                },
            )
            timeline = data.get("interest_over_time", {}).get("timeline_data", [])
            series = []
            for point in timeline:
                values = point.get("values", [])
                if values:
                    series.append(values[0].get("extracted_value", values[0].get("value", 0)))
            if len(series) < 4:
                return None
            recent_avg = sum(series[-3:]) / 3
            prev_avg = sum(series[:-3]) / max(len(series) - 3, 1)
            direction = "tăng" if recent_avg > prev_avg * 1.15 else ("giảm" if recent_avg < prev_avg * 0.85 else "ổn định")
            diff_pct = int(((recent_avg - prev_avg) / (prev_avg or 1)) * 100)
            return Evidence(
                source=self.name,
                kind="keyword_signal",
                keyword=kw,
                text=f"Chỉ số tìm kiếm Google Trends (qua SerpApi) cho '{kw}' đang ở trạng thái {direction} ({diff_pct:+d}% so với giai đoạn trước, điểm gần nhất: {int(series[-1])}/100)",
                value=f"Trend {direction} ({diff_pct:+d}%)",
                source_url=_explore_url(kw, self.date),
            )
        except Exception as e:
            logger.warning(f"SerpApi Trends interest_over_time for '{kw}' failed: {e}")
            return None
