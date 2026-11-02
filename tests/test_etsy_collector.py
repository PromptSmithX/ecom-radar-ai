"""Unit tests for Etsy collector."""

from __future__ import annotations
from unittest.mock import MagicMock, patch
import pytest
from src.collectors.etsy import EtsyCollector
from src.core.models import Evidence, Niche


@pytest.fixture
def sample_niche():
    return Niche(
        id="personalized_gift",
        name="Personalized gift",
        seed_keywords=["personalized gifts"],
    )


def test_etsy_collector_parses_listings(sample_niche):
    mock_results = [
        {
            "title": "Custom Name Leather Wallet - Etsy",
            "href": "https://www.etsy.com/listing/123456789/custom-name-leather-wallet",
            "body": "Handcrafted full-grain leather wallet with custom engraving. Price: $29.99 USD. Ships fast.",
        },
        {
            "title": "Personalized Wooden Clock - Etsy",
            "href": "https://www.etsy.com/listing/987654321/personalized-wooden-clock",
            "body": "Rustic handmade wall clock engraved with family name. Over 100 sold.",
        },
    ]

    with patch("src.collectors.etsy.DDGS") as mock_ddgs_cls:
        mock_ddgs_inst = MagicMock()
        mock_ddgs_cls.return_value = mock_ddgs_inst
        mock_ddgs_inst.text.return_value = mock_results

        collector = EtsyCollector()
        evidence_list = collector.collect(sample_niche, use_cache=False)

        assert len(evidence_list) == 2
        first = evidence_list[0]
        assert isinstance(first, Evidence)
        assert first.source == "etsy"
        assert first.kind == "price"
        assert "$29.99" in (first.value or "")
        assert first.source_url == "https://www.etsy.com/listing/123456789"
        assert "Custom Name Leather Wallet" in first.title

        second = evidence_list[1]
        assert second.kind == "competitor"
        assert second.source_url == "https://www.etsy.com/listing/987654321"
