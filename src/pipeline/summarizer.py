"""Summarizer step: Ranks niches and selects top 3 product ideas."""

from __future__ import annotations
import json
import logging
from typing import List, Tuple
from src.core.config import BASE_DIR
from src.core.models import Idea, NicheReport, RankingItem
from src.llm.base import LLMClient, Usage
from .writer import clean_json_text

logger = logging.getLogger(__name__)


def summarize_report(
    niche_reports: List[NicheReport],
    llm: LLMClient,
    max_retries: int = 2,
) -> Tuple[List[RankingItem], List[Idea], Usage]:
    """Generates ranking and picks top 3 product ideas across all niches."""
    prompt_file = BASE_DIR / "src" / "prompts" / "summary.md"
    system_prompt = prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else "You are a business strategist."

    summary_input = []
    all_niche_ideas: List[Idea] = []

    for r in niche_reports:
        all_niche_ideas.extend(r.ideas)
        summary_input.append({
            "niche": r.niche,
            "trend": r.trend,
            "score": r.score,
            "score_reason": r.score_reason,
            "analysis": r.analysis[:200],
            "price_range": r.price_range,
            "ideas_count": len(r.ideas),
            "ideas": [i.model_dump() for i in r.ideas]
        })

    user_prompt = f"""Dưới đây là tóm tắt kết quả phân tích của {len(niche_reports)} niche:

{json.dumps(summary_input, ensure_ascii=False, indent=2)}

Hãy xếp hạng tất cả các niche và chọn ra đúng 3 ý tưởng sản phẩm tốt nhất toàn diện. Trả về đúng schema JSON."""

    total_usage = Usage()

    for attempt in range(max_retries + 1):
        try:
            result = llm.generate(system=system_prompt, prompt=user_prompt, json_mode=True)
            total_usage.input_tokens += result.usage.input_tokens
            total_usage.output_tokens += result.usage.output_tokens

            cleaned = clean_json_text(result.text)
            data = json.loads(cleaned)

            raw_rankings = data.get("ranking", [])
            raw_top_ideas = data.get("top_ideas", [])

            rankings = [RankingItem(**item) for item in raw_rankings]
            top_ideas = [Idea(**item) for item in raw_top_ideas]

            # Enforce exactly 3 top ideas
            if len(top_ideas) > 3:
                top_ideas = top_ideas[:3]
            elif len(top_ideas) < 3:
                # Supplement from all_niche_ideas
                for extra in all_niche_ideas:
                    if not any(t.title == extra.title for t in top_ideas):
                        top_ideas.append(extra)
                    if len(top_ideas) == 3:
                        break

            # Fallback ranking if missing items
            if len(rankings) < len(niche_reports):
                ranked_names = {r.niche for r in rankings}
                curr_rank = len(rankings) + 1
                for nr in sorted(niche_reports, key=lambda x: x.score, reverse=True):
                    if nr.niche not in ranked_names:
                        rankings.append(
                            RankingItem(
                                rank=curr_rank,
                                niche=nr.niche,
                                score=nr.score,
                                reason=nr.score_reason or "Tiềm năng thị trường ổn định",
                            )
                        )
                        curr_rank += 1

            return rankings, top_ideas, total_usage
        except Exception as e:
            logger.warning(f"Summarizer attempt {attempt + 1} failed: {e}")

    # Programmatic fallback
    logger.warning("Summarizer failed across all retries. Falling back to programmatic ranking.")
    sorted_reports = sorted(niche_reports, key=lambda x: x.score, reverse=True)
    fallback_rankings = [
        RankingItem(
            rank=idx + 1,
            niche=nr.niche,
            score=nr.score,
            reason=nr.score_reason or f"Niche có điểm đánh giá {nr.score}/10 với xu hướng {nr.trend}",
        )
        for idx, nr in enumerate(sorted_reports)
    ]
    fallback_ideas = all_niche_ideas[:3]
    return fallback_rankings, fallback_ideas, total_usage
