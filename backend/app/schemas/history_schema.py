from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class HistorySearchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    run_id: str
    topic_id: str
    title: str
    url: str
    decision_reason: str | None = None


class HistorySearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    query: str
    top_k: int
    exclude_run_id: str | None = None
    items: list[HistorySearchItem] = Field(default_factory=list)
