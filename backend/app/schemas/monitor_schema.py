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
    run_context: dict[str, Any] = Field(default_factory=dict)
    business_memory: dict[str, Any] = Field(default_factory=dict)
    planner_output: dict[str, Any] = Field(default_factory=dict)
    retrieval_output: dict[str, Any] = Field(default_factory=dict)
    extraction_output: dict[str, Any] = Field(default_factory=dict)
    evaluation_output: dict[str, Any] = Field(default_factory=dict)
    expanded_queries: list[str] = Field(default_factory=list)
    candidate_items: list[dict[str, Any]] = Field(default_factory=list)
    final_decisions: list[dict[str, Any]] = Field(default_factory=list)
    candidate_task_summary: dict[str, Any] = Field(default_factory=dict)
    integration_runtime: dict[str, Any] = Field(default_factory=dict)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class CandidateTaskRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    run_id: str
    candidate_id: str
    stage: str
    status: str
    attempt: int
    max_attempts: int
    depends_on_task_ids: list[str] = Field(default_factory=list)
    input_ref: dict[str, Any] = Field(default_factory=dict)
    output_ref: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None


class CandidateTaskRecordListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CandidateTaskRecordResponse] = Field(default_factory=list)
