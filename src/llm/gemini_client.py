"""Gemini LLM client implementation using official google-genai SDK."""

from __future__ import annotations
import logging
from typing import Optional
from google import genai
from google.genai import types
from .base import LLMClient, LLMResult, Usage

logger = logging.getLogger(__name__)


class GeminiClient(LLMClient):
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model
        self.client = genai.Client(api_key=api_key) if api_key else None

    def generate(self, system: str, prompt: str, *, json_mode: bool = False) -> LLMResult:
        if not self.client:
            raise ValueError("GEMINI_API_KEY is not set. Please provide a valid Gemini API key in .env or via UI.")

        config_args = {}
        if system and system.strip():
            config_args["system_instruction"] = system.strip()
        if json_mode:
            config_args["response_mime_type"] = "application/json"

        config = types.GenerateContentConfig(**config_args) if config_args else None

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise e

        # Extract usage
        prompt_tokens = 0
        candidate_tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            candidate_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

        text = response.text or ""
        return LLMResult(
            text=text.strip(),
            usage=Usage(input_tokens=prompt_tokens, output_tokens=candidate_tokens),
        )
