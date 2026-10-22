"""LLM Factory for selecting and instantiating LLM clients."""

from __future__ import annotations
import json
import logging
from typing import Optional
from src.core.config import settings
from .base import LLMClient, LLMResult, Usage
from .gemini_client import GeminiClient
from .openai_client import OpenAIClient

logger = logging.getLogger(__name__)


class MockLLMClient(LLMClient):
    """Mock LLM client for offline development, dry-runs, and testing.

    All responses are clearly marked as mock data and use mock.example.com URLs.
    Never use this client for production runs intended to generate real market insights.
    """
    def __init__(self, model: str = "mock-model"):
        self.model = model

    def generate(self, system: str, prompt: str, *, json_mode: bool = False) -> LLMResult:
        logger.info(f"MockLLMClient generating response for prompt (len={len(prompt)})")
        if json_mode:
            prompt_lower = (prompt + " " + system).lower()
            if "ranking" in prompt_lower or "top_ideas" in prompt_lower or "summary" in prompt_lower:
                sample_data = {
                    "ranking": [
                        {"rank": 1, "niche": "Christmas gift ideas", "score": 5, "reason": "⚠️ DỮ LIỆU MẪU — không có dữ liệu thật"},
                        {"rank": 2, "niche": "Personalized gift", "score": 5, "reason": "⚠️ DỮ LIỆU MẪU — không có dữ liệu thật"},
                        {"rank": 3, "niche": "Gift for him", "score": 5, "reason": "⚠️ DỮ LIỆU MẪU — không có dữ liệu thật"},
                        {"rank": 4, "niche": "Valentine gift", "score": 5, "reason": "⚠️ DỮ LIỆU MẪU — không có dữ liệu thật"}
                    ],
                    "top_ideas": [
                        {
                            "title": "⚠️ DỮ LIỆU MẪU — Ý tưởng placeholder 1",
                            "what": "⚠️ Chạy với LLM thật để có ý tưởng sản phẩm thực sự",
                            "for_whom": "⚠️ Chưa xác định — cần dữ liệu thật",
                            "why_now": "⚠️ Chưa có tín hiệu thị trường thật",
                            "evidence_refs": ["https://mock.example.com/placeholder-1"]
                        },
                        {
                            "title": "⚠️ DỮ LIỆU MẪU — Ý tưởng placeholder 2",
                            "what": "⚠️ Chạy với LLM thật để có ý tưởng sản phẩm thực sự",
                            "for_whom": "⚠️ Chưa xác định — cần dữ liệu thật",
                            "why_now": "⚠️ Chưa có tín hiệu thị trường thật",
                            "evidence_refs": ["https://mock.example.com/placeholder-2"]
                        },
                        {
                            "title": "⚠️ DỮ LIỆU MẪU — Ý tưởng placeholder 3",
                            "what": "⚠️ Chạy với LLM thật để có ý tưởng sản phẩm thực sự",
                            "for_whom": "⚠️ Chưa xác định — cần dữ liệu thật",
                            "why_now": "⚠️ Chưa có tín hiệu thị trường thật",
                            "evidence_refs": ["https://mock.example.com/placeholder-3"]
                        }
                    ]
                }
                text = json.dumps(sample_data, ensure_ascii=False)
            elif "digest" in prompt_lower or "chuẩn hóa evidence pack" in prompt_lower:
                # For digest: return empty evidence so programmatic_digest takes over
                # using real raw evidence instead of fabricated entries
                sample_data = {"evidence": []}
                text = json.dumps(sample_data, ensure_ascii=False)
            else:
                # Niche report prompt - detect niche name specifically from header
                niche_target = ""
                for line in prompt.splitlines():
                    if "TÊN NICHE:" in line:
                        niche_target = line.split("TÊN NICHE:")[1].strip()
                        break

                sample_data = {
                    "niche": niche_target or "Unknown",
                    "keywords": [
                        {
                            "keyword": "⚠️ placeholder",
                            "signal": "⚠️ DỮ LIỆU MẪU — chưa có tín hiệu thật",
                            "source_url": "https://mock.example.com/keywords"
                        }
                    ],
                    "trend": "ổn định",
                    "analysis": "⚠️ DỮ LIỆU MẪU — Chạy với LLM thật (Gemini/OpenAI) để có phân tích thị trường thực sự.",
                    "customer": "⚠️ DỮ LIỆU MẪU — chưa xác định được chân dung khách hàng.",
                    "pain_points": ["⚠️ DỮ LIỆU MẪU — cần LLM thật để phân tích pain points"],
                    "competition": "⚠️ DỮ LIỆU MẪU — chưa có dữ liệu cạnh tranh thật.",
                    "price_range": "Không có dữ liệu",
                    "ideas": [
                        {
                            "title": "⚠️ DỮ LIỆU MẪU — Ý tưởng placeholder",
                            "what": "⚠️ Chạy với LLM thật để có ý tưởng sản phẩm thực sự",
                            "for_whom": "⚠️ Chưa xác định",
                            "why_now": "⚠️ Chưa có tín hiệu thị trường thật",
                            "evidence_refs": ["https://mock.example.com/niche-placeholder"]
                        }
                    ],
                    "score": 5,
                    "score_reason": "⚠️ DỮ LIỆU MẪU — điểm mặc định, không phản ánh thực tế.",
                    "is_mock": True
                }
                text = json.dumps(sample_data, ensure_ascii=False)
        else:
            text = "⚠️ DỮ LIỆU MẪU — Mock LLM không tạo báo cáo thật. Dùng Gemini hoặc OpenAI."

        return LLMResult(
            text=text,
            usage=Usage(input_tokens=50, output_tokens=100),
        )


def get_llm(
    provider: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None
) -> LLMClient:
    """Factory to retrieve the appropriate LLM client."""
    provider_clean = (provider or "").lower().strip()

    if provider_clean == "gemini":
        key = api_key or settings.gemini_api_key
        mod = model or settings.llm.writer.model or "gemini-2.5-flash"
        return GeminiClient(api_key=key, model=mod)

    if provider_clean == "openai":
        key = api_key or settings.openai_api_key
        mod = model or settings.llm.writer.model or "gpt-4o-mini"
        return OpenAIClient(api_key=key, model=mod)

    if provider_clean in ["mock", "test", "offline"]:
        return MockLLMClient(model=model or "mock-model")

    raise ValueError(f"Unknown LLM provider: '{provider}'. Supported providers: 'gemini', 'openai', 'mock'.")
