from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_PUSH_THRESHOLD = 0.72
ENV_FILE_PATH = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Industry News Agent MVP"
    database_url: str = Field(...)
    redis_url: str = Field(...)
    default_push_threshold: float = Field(default=DEFAULT_PUSH_THRESHOLD)
    mcp_gateway_provider: Literal["local", "onesearch"] = Field(default="local")
    onesearch_base_url: str | None = Field(default=None)
    onesearch_timeout_seconds: float = Field(default=10.0, gt=0.0)
    onesearch_max_results: int = Field(default=10, gt=0)
    search_provider: str = Field(default="mock")
    open_websearch_base_url: str | None = Field(default=None)
    open_websearch_timeout_seconds: float = Field(default=10.0)
    judge_provider: str = Field(default="mock")
    judge_base_url: str | None = Field(default=None)
    judge_api_key: str | None = Field(default=None)
    judge_model: str = Field(default="gpt-4o-mini")
    judge_timeout_seconds: float = Field(default=10.0)
    browser_fetch_provider: str = Field(default="none")
    playwright_mcp_base_url: str | None = Field(default=None)
    playwright_mcp_timeout_seconds: float = Field(default=10.0)
    browser_allowed_domains: list[str] = Field(default_factory=list)
    browser_max_concurrency: int = Field(default=1)
    browser_max_content_chars: int = Field(default=20000)
    history_index_provider: str = Field(default="none")
    opensearch_base_url: str | None = Field(default=None)
    opensearch_index_name: str = Field(default="industry-news-candidates")
    opensearch_timeout_seconds: float = Field(default=10.0)
    local_embedding_dimensions: int = Field(default=256, gt=0)
    local_embedding_char_ngram_min: int = Field(default=3, gt=0)
    local_embedding_char_ngram_max: int = Field(default=5, gt=0)
    local_embedding_min_score: float = Field(default=0.18, ge=0.0, le=1.0)
    candidate_fetch_concurrency: int = Field(default=2)
    candidate_extract_concurrency: int = Field(default=2)
    candidate_evaluate_concurrency: int = Field(default=2)
    semantic_dedup_provider: str = Field(default="none")
    semantic_dedup_threshold: float = Field(default=0.88, gt=0.0, le=1.0)
    notification_provider: str = Field(default="none")
    notification_webhook_url: str | None = Field(default=None)
    notification_timeout_seconds: float = Field(default=10.0, gt=0.0)

def get_settings() -> Settings:
    return Settings()
