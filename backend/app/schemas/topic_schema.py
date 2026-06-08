from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import DEFAULT_PUSH_THRESHOLD


class TopicCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    seed_keywords: list[str]
    trusted_sources: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    push_threshold: float = Field(default=DEFAULT_PUSH_THRESHOLD, ge=0.0, le=1.0)
    cooldown_hours: int = Field(default=24, ge=0)
    enabled: bool = True
    schedule_cron: str | None = None


class TopicResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    topic_id: str
    name: str
    description: str
    seed_keywords: list[str]
    trusted_sources: list[str]
    exclude_keywords: list[str]
    push_threshold: float = Field(ge=0.0, le=1.0)
    cooldown_hours: int = Field(ge=0)
    enabled: bool
    schedule_cron: str | None = None
    created_at: datetime
    updated_at: datetime
