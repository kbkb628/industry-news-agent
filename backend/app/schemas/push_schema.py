from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PushRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    push_id: str
    run_id: str
    topic_id: str
    candidate_id: str
    extracted_id: str | None = None
    should_push: bool
    score: float
    decision_reason: str | None = None
    pushed_at: datetime | None = None


class PushListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: str | None = None
    pushes: list[PushRecord]
