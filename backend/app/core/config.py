from pathlib import Path

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

def get_settings() -> Settings:
    return Settings()
