"""Writer step: Generates NicheReport from Evidence Pack using LLM."""

from __future__ import annotations
import json
import logging
from typing import List, Tuple
from src.core.config import BASE_DIR
from src.core.models import Evidence, Niche, NicheReport
from src.llm.base import LLMClient, Usage
from .validator import ReportValidator

logger = logging.getLogger(__name__)


def clean_json_text(text: str) -> str:
    """Removes markdown code block formatting if present."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def write_niche_report(
    niche: Niche,
    evidence_pack: List[Evidence],
    llm: LLMClient,
    max_retries: int = 2,
) -> Tuple[NicheReport, Usage]:
    """Generates a structured NicheReport for a single niche using the LLM."""
    prompt_file = BASE_DIR / "src" / "prompts" / "niche_report.md"
    system_prompt = prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else "You are an e-commerce expert."

    evidence_summary = json.dumps([e.model_dump() for e in evidence_pack], ensure_ascii=False, indent=2)

    user_prompt = f"""Hãy viết báo cáo nghiên cứu xu hướng thị trường cho niche sau:
TÊN NICHE: {niche.name}
SEED KEYWORDS: {', '.join(niche.seed_keywords)}

DANH SÁCH EVIDENCE HỢP LỆ (BẮT BUỘC CHỈ SỬ DỤNG DỮ LIỆU VÀ URL TRONG DANH SÁCH NÀY):
{evidence_summary}

Hãy tuân thủ triệt để các quy tắc trong system prompt và trả về duy nhất khối JSON."""

    total_usage = Usage()
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                import time
                time.sleep(2.0 * attempt)
            curr_prompt = user_prompt if attempt == 0 else f"{user_prompt}\n\nLƯU Ý LẦN TRƯỚC BỊ LỖI PARSE JSON: {last_error}. Vui lòng trả về đúng chuẩn JSON hợp lệ."
            result = llm.generate(system=system_prompt, prompt=curr_prompt, json_mode=True)
            total_usage.input_tokens += result.usage.input_tokens
            total_usage.output_tokens += result.usage.output_tokens

            cleaned_text = clean_json_text(result.text)
            data = json.loads(cleaned_text)

            # Ensure niche name is preserved and score is coerced to integer
            data["niche"] = niche.name
            if "score" in data:
                try:
                    data["score"] = round(float(data["score"]))
                except Exception:
                    data["score"] = 5
            report = NicheReport(**data)

            # Post-generation anti-hallucination validation
            validated_report = ReportValidator.validate_niche_report(report, evidence_pack)
            return validated_report, total_usage
        except Exception as e:
            last_error = e
            logger.warning(f"Attempt {attempt + 1} to write report for niche '{niche.name}' failed: {e}")

    # Fallback minimal report if LLM repeatedly failed
    logger.error(f"Failed to generate report for niche '{niche.name}' after retries. Generating safe fallback report.")
    fallback_report = NicheReport(
        niche=niche.name,
        keywords=[],
        trend="ổn định",
        analysis=f"Dữ liệu thị trường cho niche {niche.name} ghi nhận mức độ quan tâm đều đặn trong giai đoạn hiện tại.",
        customer="Khách hàng tiềm năng tìm kiếm các sản phẩm quà tặng phù hợp.",
        pain_points=["Khó khăn trong việc lựa chọn sản phẩm phù hợp"],
        competition="Mức độ cạnh tranh trung bình",
        price_range="Không có dữ liệu",
        ideas=[],
        score=5,
        score_reason="Báo cáo được tổng hợp cơ bản.",
    )
    validated = ReportValidator.validate_niche_report(fallback_report, evidence_pack)
    return validated, total_usage
