"""Base class for data collectors."""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List
from src.core.models import Evidence, Niche


class Collector(ABC):
    """Abstract base class for all collectors."""
    name: str = "base"

    @abstractmethod
    def collect(self, niche: Niche) -> List[Evidence]:
        """Collects evidence for the given niche.
        Must return a list of Evidence items, each containing a valid source_url.
        """
        pass
