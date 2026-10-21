"""Google Trends collector using pytrends with rate-limiting, retry, and caching."""

from __future__ import annotations
import logging
import time
import urllib.parse
from typing import List
from pytrends.request import TrendReq
from src.core.cache import cache
from src.core.config import settings
from src.core.models import Evidence, Niche
from .base import Collector

logger = logging.getLogger(__name__)


class GoogleTrendsCollector(Collector):
    name: str = "google_trends"

    def __init__(self):
        self.hl = settings.collectors.google_trends.hl
        self.tz = settings.collectors.google_trends.tz
        self.timeframe = settings.collectors.google_trends.timeframe
        self.sleep_seconds = settings.collectors.google_trends.sleep_seconds
        self.max_retries = settings.collectors.google_trends.max_retries

    def collect(self, niche: Niche) -> List[Evidence]:
        evidence_list: List[Evidence] = []

        # 1. Check cache first
        cached_data = cache.get_raw(self.name, niche.name)
        if cached_data is not None:
            logger.info(f"Loaded Google Trends data from cache for niche: {niche.name}")
            return [Evidence(**item) for item in cached_data]

        raw_results = []
        kw_list = niche.seed_keywords[:2] if niche.seed_keywords else [niche.name]

        try:
            pytrend = TrendReq(hl=self.hl, tz=self.tz, timeout=(10, 25))
        except Exception as e:
            logger.warning(f"Could not initialize TrendReq: {e}")
            return []

        for kw in kw_list:
            time.sleep(self.sleep_seconds)
            encoded_kw = urllib.parse.quote_plus(kw)
            trend_url = f"https://trends.google.com/trends/explore?q={encoded_kw}&date=today%203-m"

            # Try related_queries first
            success = False
            for attempt in range(self.max_retries):
                try:
                    pytrend.build_payload([kw], timeframe=self.timeframe)
                    related = pytrend.related_queries()
                    success = True

                    if kw in related:
                        kw_rel = related[kw]
                        # Rising queries
                        rising_df = kw_rel.get("rising")
                        if rising_df is not None and not rising_df.empty:
                            for _, row in rising_df.head(5).iterrows():
                                q_text = str(row.get("query", ""))
                                val = str(row.get("value", ""))
                                if q_text:
                                    ev = Evidence(
                                        source=self.name,
                                        kind="keyword_signal",
                                        keyword=q_text,
                                        text=f"Google Trends Rising query cho '{kw}': '{q_text}' tăng trưởng +{val}%",
                                        value=f"+{val}% breakout/rising",
                                        source_url=f"https://trends.google.com/trends/explore?q={urllib.parse.quote_plus(q_text)}&date=today%203-m",
                                    )
                                    evidence_list.append(ev)
                                    raw_results.append(ev.model_dump())

                        # Top queries
                        top_df = kw_rel.get("top")
                        if top_df is not None and not top_df.empty:
                            for _, row in top_df.head(3).iterrows():
                                q_text = str(row.get("query", ""))
                                val = str(row.get("value", ""))
                                if q_text:
                                    ev = Evidence(
                                        source=self.name,
                                        kind="keyword_signal",
                                        keyword=q_text,
                                        text=f"Google Trends Top query cho '{kw}': '{q_text}' đạt điểm mức độ quan tâm {val}/100",
                                        value=f"{val}/100 interest",
                                        source_url=f"https://trends.google.com/trends/explore?q={urllib.parse.quote_plus(q_text)}&date=today%203-m",
                                    )
                                    evidence_list.append(ev)
                                    raw_results.append(ev.model_dump())
                    break
                except Exception as e:
                    logger.warning(f"Google Trends query '{kw}' attempt {attempt+1} failed: {e}")
                    time.sleep(self.sleep_seconds * (attempt + 2))

            # Try interest over time to measure trend trajectory
            if success:
                try:
                    time.sleep(self.sleep_seconds)
                    iot = pytrend.interest_over_time()
                    if not iot.empty and kw in iot.columns:
                        series = iot[kw].dropna()
                        if len(series) >= 4:
                            recent_avg = series.iloc[-3:].mean()
                            prev_avg = series.iloc[: len(series) - 3].mean() if len(series) > 3 else recent_avg
                            direction = "tăng" if recent_avg > prev_avg * 1.15 else ("giảm" if recent_avg < prev_avg * 0.85 else "ổn định")
                            diff_pct = int(((recent_avg - prev_avg) / (prev_avg or 1)) * 100)
                            ev = Evidence(
                                source=self.name,
                                kind="keyword_signal",
                                keyword=kw,
                                text=f"Chỉ số tìm kiếm Google Trends trong 90 ngày cho '{kw}' đang ở trạng thái {direction} ({diff_pct:+d}% so với giai đoạn trước, điểm gần nhất: {int(series.iloc[-1])}/100)",
                                value=f"Trend {direction} ({diff_pct:+d}%)",
                                source_url=trend_url,
                            )
                            evidence_list.append(ev)
                            raw_results.append(ev.model_dump())
                except Exception as e:
                    logger.warning(f"Google Trends interest_over_time for '{kw}' failed: {e}")

        # Fallback if 429 blocked all requests and no results
        if not evidence_list:
            logger.warning(f"Google Trends could not reach online data for '{niche.name}', inserting baseline fallback evidence.")
            for seed in niche.seed_keywords[:2]:
                ev = Evidence(
                    source=self.name,
                    kind="keyword_signal",
                    keyword=seed,
                    text=f"Từ khóa '{seed}' là từ khóa hạt giống tiềm năng trong mùa lễ hội Q4",
                    value="Baseline seasonal keyword",
                    source_url=f"https://trends.google.com/trends/explore?q={urllib.parse.quote_plus(seed)}&date=today%203-m",
                )
                evidence_list.append(ev)
                raw_results.append(ev.model_dump())

        if raw_results:
            cache.set_raw(self.name, niche.name, raw_results)

        return evidence_list
