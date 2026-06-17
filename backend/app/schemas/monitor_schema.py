from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MonitorRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class MonitorRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    topic_id: str
    trigger: str
    status: MonitorRunStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None


class MonitorRunStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    topic_id: str
    trigger: str
    status: MonitorRunStatus
    expanded_queries: list[str] = Field(default_factory=list)
    candidate_items: list[dict[str, Any]] = Field(default_factory=list)
    final_decisions: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
