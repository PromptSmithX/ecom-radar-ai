"""Tests for LLM clients, factory, and cost tracking."""

from __future__ import annotations
import pytest
from src.llm.base import LLMClient, LLMResult, Usage
from src.llm.cost import calculate_cost, MODEL_PRICING
from src.llm.factory import get_llm, MockLLMClient


def test_mock_llm_generation():
    client = get_llm("mock")
    assert isinstance(client, MockLLMClient)
    res = client.generate(system="", prompt="test prompt", json_mode=False)
    assert isinstance(res, LLMResult)
    assert len(res.text) > 0
    assert res.usage.input_tokens > 0


def test_mock_llm_json_mode():
    client = get_llm("mock")
    res = client.generate(system="DIGEST EVIDENCE", prompt="chuẩn hóa evidence pack", json_mode=True)
    assert isinstance(res, LLMResult)
    assert "evidence" in res.text


def test_unknown_provider():
    with pytest.raises(ValueError):
        get_llm("unknown_provider_xyz")


def test_calculate_cost():
    # Test gemini pricing: 1M in = $0.075, 1M out = $0.30
    cost = calculate_cost("gemini-2.5-flash", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.375, 0.001)

    # Test small token count
    small_cost = calculate_cost("gemini-2.5-flash", 1000, 2000)
    assert small_cost > 0.0
    assert small_cost < 0.01
