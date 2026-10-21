"""OpenAI LLM client implementation."""

from __future__ import annotations
import logging
from typing import Optional
from openai import OpenAI
from .base import LLMClient, LLMResult, Usage

logger = logging.getLogger(__name__)


class OpenAIClient(LLMClient):
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.client = OpenAI(api_key=api_key) if api_key else None

    def generate(self, system: str, prompt: str, *, json_mode: bool = False) -> LLMResult:
        if not self.client:
            raise ValueError("OPENAI_API_KEY is not set. Please provide a valid OpenAI API key in .env or via UI.")

        messages = []
        if system and system.strip():
            messages.append({"role": "system", "content": system.strip()})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": self.model,
            "messages": messages,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise e

        choice = response.choices[0]
        text = choice.message.content or ""

        prompt_tokens = response.usage.prompt_tokens if response.usage else 0
        completion_tokens = response.usage.completion_tokens if response.usage else 0

        return LLMResult(
            text=text.strip(),
            usage=Usage(input_tokens=prompt_tokens, output_tokens=completion_tokens),
        )
