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
    push_count: int = Field(ge=0)
    tool_success_rate: float = Field(ge=0.0, le=1.0)
    suggestions: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
