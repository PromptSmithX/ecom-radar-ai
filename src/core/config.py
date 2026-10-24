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


class SerpApiConfig(BaseModel):
    hl: str = "en"
    geo: str = "US"
    date: str = "today 3-m"
    cooldown_minutes: int = 60
    include_interest_over_time: bool = False


class RedditConfig(BaseModel):
    # Reddit is sourced through Tavily: the public JSON endpoint now returns 403
    # because Reddit forces login for anonymous search.
    use_tavily: bool = True
    time_range: str = "year"
    search_depth: str = "basic"  # basic (1 credit) | advanced (2 credits)

    # Credit budget: max_seeds x max_intents x max_queries_per_intent = queries per niche.
    # Defaults give exactly 2 Tavily queries (= 2 credits) per niche: pain + regret.
    max_seeds: int = 1
    max_intents: int = 2
    max_queries_per_intent: int = 1
    # Tavily bills per search, not per result, so a larger page size is free.
    max_results_per_query: int = 10

    preferred_subreddits: List[str] = Field(
        default_factory=lambda: ["gifts", "GiftIdeas", "BuyItForLife", "AskMen", "AskWomen", "Etsy"]
    )
    # Order matters: with max_intents=2 only the first 2 intents run. "pain" and
    # "regret" lead because they surface the signals that matter most for product
    # risk — what's frustrating buyers right now, and what they regret buying —
    # ahead of "ask"/"recommend" which are lower-value for that decision.
    intents: Dict[str, List[str]] = Field(
        default_factory=lambda: {
            "pain": [
                "{seed} hard to choose",
                "{seed} who has everything",
            ],
            "regret": [
                "{seed} waste of money",
                "regret buying {seed}",
            ],
            "ask": [
                "looking for {seed}",
                "what should I get {seed}",
            ],
            "recommend": [
                "best {seed} worth it",
                "{seed} actually use",
            ],
        }
    )


class WebSearchConfig(BaseModel):
    max_results: int = 5


class GoogleSuggestConfig(BaseModel):
    client: str = "firefox"
    hl: str = "en"
    # Tried in order; the first provider that answers wins. Google rate-limits (429)
    # an IP after repeated runs, so DuckDuckGo and Bing act as drop-in backups —
    # all three return the same ["query", [suggestions...]] shape.
    providers: List[str] = Field(default_factory=lambda: ["google", "duckduckgo", "bing"])
    request_delay: float = 1.0
    max_suggestions: int = 6


class CollectorsConfig(BaseModel):
    trend_provider: str = "google_trends"  # "google_trends" | "serpapi"
    google_trends: GoogleTrendsConfig = Field(default_factory=GoogleTrendsConfig)
    serpapi: SerpApiConfig = Field(default_factory=SerpApiConfig)
    reddit: RedditConfig = Field(default_factory=RedditConfig)
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    google_suggest: GoogleSuggestConfig = Field(default_factory=GoogleSuggestConfig)


class DigestConfig(BaseModel):
    max_items: int = 25  # cap for the programmatic (no-LLM) digest
    max_items_llm: int = 35  # cap for what gets fed into the LLM digest prompt
    # Evidence is picked round-robin across sources in this order, so a source that
    # returns many cheap items (google_suggest) can't crowd out the expensive,
    # hard-to-get ones (reddit) by simply arriving first.
    source_priority: List[str] = Field(
        default_factory=lambda: [
            "reddit",
            "serpapi_trends",
            "google_trends",
            "web_search",
            "google_suggest",
        ]
    )


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
    serpapi_api_key: Optional[str] = Field(default=None, alias="SERPAPI_API_KEY")
    reddit_user_agent: str = Field(default="trend-research/0.1 (by ecomm-researcher)", alias="REDDIT_USER_AGENT")

    # Settings from YAML
    llm: LLMConfig = Field(default_factory=LLMConfig)
    collectors: CollectorsConfig = Field(default_factory=CollectorsConfig)
    digest: DigestConfig = Field(default_factory=DigestConfig)
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
