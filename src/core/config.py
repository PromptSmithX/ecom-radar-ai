"""Configuration loader for the Trend Research Tool."""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from .models import Niche

# Base project paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"


class LLMStepConfig(BaseModel):
    provider: str = "gemini"  # "gemini" | "openai"
    model: str = "gemini-2.5-flash"


class LLMConfig(BaseModel):
    digest: LLMStepConfig = Field(default_factory=lambda: LLMStepConfig(provider="gemini", model="gemini-2.5-flash"))
    writer: LLMStepConfig = Field(default_factory=lambda: LLMStepConfig(provider="gemini", model="gemini-2.5-flash"))
    summary: LLMStepConfig = Field(default_factory=lambda: LLMStepConfig(provider="gemini", model="gemini-2.5-flash"))


class GoogleTrendsConfig(BaseModel):
    hl: str = "en-US"
    tz: int = 360
    timeframe: str = "today 3-m"
    sleep_seconds: float = 2.0
    max_retries: int = 3
    cooldown_minutes: int = 60


class RedditConfig(BaseModel):
    max_results_per_query: int = 5
    time_range: str = "year"
    search_depth: str = "advanced"
    max_queries_per_intent: Optional[int] = None
    preferred_subreddits: List[str] = Field(
        default_factory=lambda: ["gifts", "GiftIdeas", "BuyItForLife", "AskMen", "AskWomen", "Etsy"]
    )
    intents: Dict[str, List[str]] = Field(
        default_factory=lambda: {
            "ask": [
                "looking for {seed}",
                "what should I get {seed}",
            ],
            "pain": [
                "{seed} hard to choose",
                "{seed} who has everything",
            ],
            "regret": [
                "{seed} waste of money",
                "regret buying {seed}",
            ],
            "recommend": [
                "best {seed} worth it",
                "{seed} actually use",
            ],
        }
    )
    limit: Optional[int] = 10
    sort: Optional[str] = "relevance"
    time_filter: Optional[str] = "month"


class WebSearchConfig(BaseModel):
    max_results: int = 5


class GoogleSuggestConfig(BaseModel):
    client: str = "firefox"
    hl: str = "en"


class CollectorsConfig(BaseModel):
    google_trends: GoogleTrendsConfig = Field(default_factory=GoogleTrendsConfig)
    reddit: RedditConfig = Field(default_factory=RedditConfig)
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    google_suggest: GoogleSuggestConfig = Field(default_factory=GoogleSuggestConfig)


class CacheConfig(BaseModel):
    enabled: bool = True
    ttl_days: int = 1
    raw_dir: str = "data/raw"
    evidence_dir: str = "data/evidence"


class ReportingConfig(BaseModel):
    output_dir: str = "reports"
    template_path: str = "src/render/report.md.j2"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Environment variables
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    tavily_api_key: Optional[str] = Field(default=None, alias="TAVILY_API_KEY")
    reddit_user_agent: str = Field(default="trend-research/0.1 (by ecomm-researcher)", alias="REDDIT_USER_AGENT")

    # Settings from YAML
    llm: LLMConfig = Field(default_factory=LLMConfig)
    collectors: CollectorsConfig = Field(default_factory=CollectorsConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    reporting: ReportingConfig = Field(default_factory=ReportingConfig)


def load_yaml(path: Path) -> Dict[str, Any]:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def load_settings() -> Settings:
    settings_file = CONFIG_DIR / "settings.yaml"
    yaml_data = load_yaml(settings_file)
    return Settings(**yaml_data)


def load_niches() -> tuple[str, List[Niche]]:
    """Loads category and niche list from config/niches.yaml."""
    niches_file = CONFIG_DIR / "niches.yaml"
    data = load_yaml(niches_file)
    category = data.get("category", "Quà tặng theo mùa")
    niches_raw = data.get("niches", [])
    niches = [Niche(**n) for n in niches_raw]
    return category, niches


# Global settings singleton
settings = load_settings()
