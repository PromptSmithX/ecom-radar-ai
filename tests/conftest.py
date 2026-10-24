"""Shared pytest fixtures."""

from __future__ import annotations
import pytest
from src.core.cache import cache


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path, monkeypatch):
    """Points the global cache singleton at a per-test temp directory so running the
    test suite never writes into the real data/raw and data/evidence folders.

    Without this, collectors that write regardless of use_cache (google_suggest,
    web_search, serpapi_trends, and now reddit) leave real cache files behind every
    test run — e.g. reddit_query_test_cache_kw_*.json polluting real dev data.
    """
    raw_dir = tmp_path / "raw"
    evidence_dir = tmp_path / "evidence"
    raw_dir.mkdir()
    evidence_dir.mkdir()
    monkeypatch.setattr(cache, "raw_dir", raw_dir)
    monkeypatch.setattr(cache, "evidence_dir", evidence_dir)
