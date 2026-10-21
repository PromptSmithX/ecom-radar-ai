"""Cost calculation for LLM tokens across providers and models."""

from __future__ import annotations
from typing import Dict, Tuple

# Pricing in USD per 1 Million tokens: (input_price_per_1M, output_price_per_1M)
MODEL_PRICING: Dict[str, Tuple[float, float]] = {
    # Gemini models
    "gemini-2.5-flash": (0.075, 0.30),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    # OpenAI models
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}

DEFAULT_PRICING = (0.15, 0.60)


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculates total cost in USD for a given model and token counts."""
    # Find closest model name
    pricing = DEFAULT_PRICING
    for m_key, m_pricing in MODEL_PRICING.items():
        if m_key in model.lower():
            pricing = m_pricing
            break

    input_cost = (input_tokens / 1_000_000.0) * pricing[0]
    output_cost = (output_tokens / 1_000_000.0) * pricing[1]
    return round(input_cost + output_cost, 6)
