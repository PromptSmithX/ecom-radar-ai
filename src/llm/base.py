"""Base interfaces for LLM clients."""

from __future__ import annotations
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field


class Usage(BaseModel):
    input_tokens: int = Field(default=0, description="Số lượng prompt / input tokens")
    output_tokens: int = Field(default=0, description="Số lượng completion / output tokens")


class LLMResult(BaseModel):
    text: str = Field(..., description="Nội dung văn bản được sinh ra từ LLM")
    usage: Usage = Field(default_factory=Usage, description="Thống kê token tiêu thụ")


class LLMClient(ABC):
    model: str

    @abstractmethod
    def generate(self, system: str, prompt: str, *, json_mode: bool = False) -> LLMResult:
        """Sinh văn bản hoặc JSON từ LLM dựa trên system prompt và user prompt."""
        pass
