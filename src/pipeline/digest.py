"""Digest step: Processes raw evidence into a structured Evidence Pack."""

from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple
from src.core.cache import cache
from src.core.config import BASE_DIR
from src.core.models import Evidence, Niche
from src.llm.base import LLMClient, Usage

logger = logging.getLogger(__name__)


def programmatic_digest(raw_evidence: List[Evidence], max_items: int = 25) -> List[Evidence]:
    """Fallback deduplication and clean-up without LLM."""
    seen_urls = set()
    cleaned: List[Evidence] = []
    for item in raw_evidence:
        if not item.source_url or item.source_url in seen_urls:
            continue
        seen_urls.add(item.source_url)
        cleaned.append(item)
        if len(cleaned) >= max_items:
            break
    return cleaned


def digest_step(
    niche: Niche,
    raw_evidence: List[Evidence],
    llm: Optional[LLMClient] = None,
    use_cache: bool = True,
) -> Tuple[List[Evidence], Usage]:
    """Digests raw collected evidence into a clean Evidence Pack.
    Uses cached evidence pack if available.
    """
    total_usage = Usage()

    # 1. Check cached evidence pack
    if use_cache:
        cached_evidence = cache.get_evidence(niche.name)
        if cached_evidence is not None and len(cached_evidence) > 0:
            logger.info(f"Loaded digested evidence pack from cache for niche: {niche.name}")
            return cached_evidence, total_usage

    if not raw_evidence:
        logger.warning(f"No raw evidence found to digest for niche: {niche.name}")
        return [], total_usage

    # If no LLM client provided, use programmatic digest
    if llm is None:
        digested = programmatic_digest(raw_evidence)
        cache.set_evidence(niche.name, digested)
        return digested, total_usage

    # 2. Run LLM Digest
    prompt_file = BASE_DIR / "src" / "prompts" / "digest.md"
    system_prompt = prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else "You are an e-commerce market researcher."

    raw_evidence_json = json.dumps([e.model_dump() for e in raw_evidence[:35]], ensure_ascii=False, indent=2)
    user_prompt = f"""Dưới đây là danh sách dữ liệu thô thu thập được cho niche '{niche.name}':

{raw_evidence_json}

Hãy lọc trùng, chuẩn hóa và trả về Evidence Pack theo đúng định dạng JSON."""

    try:
        result = llm.generate(system=system_prompt, prompt=user_prompt, json_mode=True)
        total_usage = result.usage

        # Parse output JSON
        text = result.text.strip()
        # Strip potential markdown fences
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        parsed = json.loads(text.strip())
        items = parsed.get("evidence", [])
        evidence_pack = [Evidence(**item) for item in items if "source_url" in item and item["source_url"]]

        if not evidence_pack:
            logger.warning(f"LLM returned empty evidence pack for {niche.name}. Using programmatic fallback.")
            evidence_pack = programmatic_digest(raw_evidence)
    except Exception as e:
        logger.warning(f"LLM Digest step failed for '{niche.name}': {e}. Using programmatic digest.")
        evidence_pack = programmatic_digest(raw_evidence)

    # Save to cache
    cache.set_evidence(niche.name, evidence_pack)
    return evidence_pack, total_usage
