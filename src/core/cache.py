"""File-based caching mechanism for raw collected data and evidence packs."""

from __future__ import annotations
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional
from .config import BASE_DIR, settings
from .models import Evidence


def sanitize_filename(name: str) -> str:
    """Replaces non-alphanumeric characters with underscores."""
    return re.sub(r"[^\w\-_.]", "_", name).strip("_")


class CacheManager:
    def __init__(self, raw_dir: Optional[Path] = None, evidence_dir: Optional[Path] = None):
        self.raw_dir = raw_dir or (BASE_DIR / settings.cache.raw_dir)
        self.evidence_dir = evidence_dir or (BASE_DIR / settings.cache.evidence_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def _is_expired(self, file_path: Path, ttl_days: int) -> bool:
        if not file_path.exists():
            return True
        if ttl_days <= 0:
            return False
        file_age_seconds = time.time() - file_path.stat().st_mtime
        return file_age_seconds > (ttl_days * 86400)

    def get_raw(self, source: str, key: str, ttl_days: Optional[int] = None) -> Optional[Any]:
        if not settings.cache.enabled:
            return None
        ttl = ttl_days if ttl_days is not None else settings.cache.ttl_days
        filename = f"{sanitize_filename(source)}_{sanitize_filename(key)}.json"
        file_path = self.raw_dir / filename

        if not file_path.exists() or self._is_expired(file_path, ttl):
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("payload")
        except Exception:
            return None

    def set_raw(self, source: str, key: str, payload: Any) -> None:
        if not settings.cache.enabled:
            return
        filename = f"{sanitize_filename(source)}_{sanitize_filename(key)}.json"
        file_path = self.raw_dir / filename
        data = {
            "source": source,
            "key": key,
            "cached_at": datetime.now().isoformat(),
            "payload": payload,
        }
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_evidence(self, niche_name: str, ttl_days: Optional[int] = None) -> Optional[List[Evidence]]:
        if not settings.cache.enabled:
            return None
        ttl = ttl_days if ttl_days is not None else settings.cache.ttl_days
        filename = f"evidence_{sanitize_filename(niche_name)}.json"
        file_path = self.evidence_dir / filename

        if not file_path.exists() or self._is_expired(file_path, ttl):
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                items = data.get("evidence", [])
                return [Evidence(**item) for item in items]
        except Exception:
            return None

    def set_evidence(self, niche_name: str, evidence: List[Evidence]) -> None:
        if not settings.cache.enabled:
            return
        filename = f"evidence_{sanitize_filename(niche_name)}.json"
        file_path = self.evidence_dir / filename
        data = {
            "niche": niche_name,
            "cached_at": datetime.now().isoformat(),
            "evidence": [item.model_dump() for item in evidence],
        }
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_meta(self, key: str) -> Optional[dict]:
        """Generic small state store (e.g. circuit-breaker cooldowns), not subject to TTL."""
        filename = f"_meta_{sanitize_filename(key)}.json"
        file_path = self.raw_dir / filename
        if not file_path.exists():
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def set_meta(self, key: str, data: dict) -> None:
        filename = f"_meta_{sanitize_filename(key)}.json"
        file_path = self.raw_dir / filename
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def clear(self) -> None:
        """Removes all cached files."""
        for p in self.raw_dir.glob("*.json"):
            try:
                p.unlink()
            except Exception:
                pass
        for p in self.evidence_dir.glob("*.json"):
            try:
                p.unlink()
            except Exception:
                pass


# Global cache instance
cache = CacheManager()
