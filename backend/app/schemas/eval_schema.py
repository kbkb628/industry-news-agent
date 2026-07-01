from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EvalResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eval_id: str
    run_id: str
    topic_id: str
    retrieved_count: int = Field(ge=0)
    deduped_count: int = Field(ge=0)
    dedup_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    push_count: int = Field(ge=0)
    duplicate_push_count: int = Field(default=0, ge=0)
    tool_success_rate: float = Field(ge=0.0, le=1.0)
    fetch_success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    trace_completeness: float = Field(default=0.0, ge=0.0, le=1.0)
    raw_summary_count: int = Field(default=0, ge=0)
    browser_fallback_count: int = Field(default=0, ge=0)
    provider_fallback_count: int = Field(default=0, ge=0)
    candidate_recall_proxy: float = Field(default=0.0, ge=0.0, le=1.0)
    false_positive_proxy_count: int = Field(default=0, ge=0)
    candidate_task_failure_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_event_latency_ms: int = Field(default=0, ge=0)
    runtime_cost_proxy: dict[str, int] = Field(default_factory=dict)
    judge_mode: str = "mock_rule_judge"
    judge_score: float = Field(default=1.0, ge=0.0, le=1.0)
    judge_reason: str = "Mock judge found no rule-based quality issues."
    judge_issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class EvalSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_count: int = Field(ge=1)
    total_push_count: int = Field(ge=0)
    total_duplicate_push_count: int = Field(ge=0)
    total_raw_summary_count: int = Field(ge=0)
    total_browser_fallback_count: int = Field(ge=0)
    total_provider_fallback_count: int = Field(ge=0)
    total_false_positive_proxy_count: int = Field(ge=0)
    avg_tool_success_rate: float = Field(ge=0.0, le=1.0)
    avg_fetch_success_rate: float = Field(ge=0.0, le=1.0)
    avg_trace_completeness: float = Field(ge=0.0, le=1.0)
    avg_candidate_recall_proxy: float = Field(ge=0.0, le=1.0)
    avg_candidate_task_failure_rate: float = Field(ge=0.0, le=1.0)
    avg_event_latency_ms: int = Field(ge=0)
    latest_eval: EvalResultResponse
