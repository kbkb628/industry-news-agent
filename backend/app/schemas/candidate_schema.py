from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, HttpUrl


class CandidateSourceType(StrEnum):
    RSS = "rss"
    SEARCH = "search"
    BROWSER_FETCH = "browser_fetch"


class CandidateFetchStatus(StrEnum):
    PENDING = "pending"
    FETCHED = "fetched"
    FAILED = "failed"
    SKIPPED = "skipped"


class CandidateItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    run_id: str
    topic_id: str
    source_type: CandidateSourceType
    source_name: str
    title: str
    url: HttpUrl
    published_at: datetime | None = None
    raw_summary: str | None = None
    fetch_status: CandidateFetchStatus = CandidateFetchStatus.PENDING


class CandidateListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    candidates: list[CandidateItem]
