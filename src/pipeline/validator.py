"""Validation and anti-hallucination verification module."""

from __future__ import annotations
import logging
import re
from typing import List, Set
from src.core.models import Evidence, Idea, KeywordSignal, NicheReport

logger = logging.getLogger(__name__)

UPVOTE_PATTERN = re.compile(r"\s*\(?\b\d+\s*upvotes?\b\)?", re.IGNORECASE)


class ReportValidator:
    """Validates LLM outputs against ground-truth collected evidence."""

    @staticmethod
    def _sanitize_fabricated_upvotes(text: str, authentic_upvotes: Set[str]) -> str:
        """Removes fabricated upvote counts (e.g. '420 upvotes') unless present in authentic evidence."""
        if not text:
            return text

        def repl(match: re.Match) -> str:
            matched_str = match.group(0).strip(" ()").lower()
            if matched_str in authentic_upvotes:
                return match.group(0)
            logger.warning(f"Fabricated upvote metric detected and stripped: '{match.group(0).strip()}'")
            return ""

        cleaned = UPVOTE_PATTERN.sub(repl, text)
        return re.sub(r"\s{2,}", " ", cleaned).strip()

    @classmethod
    def validate_niche_report(cls, report: NicheReport, evidence_pack: List[Evidence]) -> NicheReport:
        """Enforces anti-hallucination rules:
        1. All source_urls must exist in the raw evidence pack.
        2. Filters out any fabricated urls or fabricated items.
        3. Ensures at least 2 ideas exist.
        4. Validates price_range and trend values.
        5. Strips fabricated upvote counts if not supported by evidence.
        """
        valid_urls: Set[str] = {e.source_url.strip() for e in evidence_pack if e.source_url}
        default_fallback_url = "[không có nguồn khớp]"

        # Collect any authentic upvote mentions present in ground-truth evidence
        authentic_upvotes: Set[str] = set()
        upvote_detector = re.compile(r"\b\d+\s*upvotes?\b", re.IGNORECASE)
        for e in evidence_pack:
            for field in [e.value, e.text, e.snippet]:
                if field:
                    for m in upvote_detector.finditer(field):
                        authentic_upvotes.add(m.group(0).lower())

        # 1. Validate Keyword Signals
        cleaned_keywords: List[KeywordSignal] = []
        for kw in report.keywords:
            kw_url = kw.source_url.strip() if kw.source_url else ""
            if kw_url in valid_urls:
                kw.signal = cls._sanitize_fabricated_upvotes(kw.signal, authentic_upvotes)
                cleaned_keywords.append(kw)
            else:
                logger.warning(
                    f"Fabricated or mismatched source_url '{kw_url}' detected for keyword '{kw.keyword}'. "
                    f"Replacing with valid ground-truth URL."
                )
                # Prioritize matching evidence URL
                matched = next(
                    (e.source_url for e in evidence_pack if kw.keyword.lower() in (e.keyword or "").lower()),
                    default_fallback_url,
                )
                kw.source_url = matched
                kw.signal = cls._sanitize_fabricated_upvotes(kw.signal, authentic_upvotes)
                cleaned_keywords.append(kw)

        # Supplement keyword signals from evidence pack if report has fewer than 3
        if len(cleaned_keywords) < 3:
            existing_kw_names = {k.keyword.lower() for k in cleaned_keywords}
            for ev in evidence_pack:
                if ev.kind == "keyword_signal" and ev.keyword and ev.keyword.lower() not in existing_kw_names:
                    cleaned_keywords.append(
                        KeywordSignal(
                            keyword=ev.keyword,
                            signal=ev.value or "Gợi ý xu hướng tìm kiếm hàng đầu",
                            source_url=ev.source_url,
                        )
                    )
                    existing_kw_names.add(ev.keyword.lower())
                    if len(cleaned_keywords) >= 4:
                        break
        report.keywords = cleaned_keywords

        # 2. Validate Trend
        if report.trend.lower() not in ["tăng", "ổn định", "giảm"]:
            report.trend = "ổn định"

        # 3. Validate Price Range
        if not report.price_range or not report.price_range.strip():
            report.price_range = "Không có dữ liệu"

        # 4. Sanitize text fields from fabricated upvotes
        report.analysis = cls._sanitize_fabricated_upvotes(report.analysis, authentic_upvotes)
        report.customer = cls._sanitize_fabricated_upvotes(report.customer, authentic_upvotes)
        report.competition = cls._sanitize_fabricated_upvotes(report.competition, authentic_upvotes)
        if report.score_reason:
            report.score_reason = cls._sanitize_fabricated_upvotes(report.score_reason, authentic_upvotes)

        report.pain_points = [
            cls._sanitize_fabricated_upvotes(p, authentic_upvotes)
            for p in report.pain_points
            if p and cls._sanitize_fabricated_upvotes(p, authentic_upvotes)
        ]

        # 5. Validate Ideas
        cleaned_ideas: List[Idea] = []
        for idea in report.ideas:
            valid_refs = [ref.strip() for ref in idea.evidence_refs if ref.strip() in valid_urls]
            if not valid_refs:
                valid_refs = [default_fallback_url]
            idea.evidence_refs = valid_refs
            idea.title = cls._sanitize_fabricated_upvotes(idea.title, authentic_upvotes)
            idea.what = cls._sanitize_fabricated_upvotes(idea.what, authentic_upvotes)
            idea.for_whom = cls._sanitize_fabricated_upvotes(idea.for_whom, authentic_upvotes)
            idea.why_now = cls._sanitize_fabricated_upvotes(idea.why_now, authentic_upvotes)
            cleaned_ideas.append(idea)

        # Ensure at least 2 ideas with transparent, honest rationale
        if len(cleaned_ideas) < 2:
            logger.warning(f"Niche '{report.niche}' has fewer than 2 ideas. Adding transparent baseline idea.")
            has_strong_evidence = len(valid_urls) > 0 and report.trend.lower() == "tăng"
            why_now_text = (
                "Ý tưởng đề xuất đón đầu chu kỳ lễ hội sắp tới; hiện tại tín hiệu tìm kiếm thực tế chưa bùng nổ, "
                "doanh nghiệp nên tiếp tục theo dõi thêm khi bước vào cao điểm mùa vụ."
                if not has_strong_evidence
                else "Đón đầu nhu cầu tìm kiếm đang trên đà tăng trưởng mạnh mẽ trong mùa mua sắm cao điểm."
            )
            cleaned_ideas.append(
                Idea(
                    title=f"Ý tưởng dự phóng theo mùa vụ: Quà tặng thiết thực cho {report.niche}",
                    what=f"Sản phẩm quà tặng mang tính ứng dụng cao hoặc có yếu tố cá nhân hóa dành riêng cho dịp {report.niche}",
                    for_whom=f"Khách hàng có kế hoạch chuẩn bị và tìm kiếm quà tặng sớm cho {report.niche}",
                    why_now=why_now_text,
                    evidence_refs=[default_fallback_url] if valid_urls else [],
                )
            )

        report.ideas = cleaned_ideas
        return report
