from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventType(StrEnum):
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    FALLBACK_USED = "fallback_used"
    NOTIFICATION_SENT = "notification_sent"
    NOTIFICATION_SKIPPED = "notification_skipped"


class MonitorNodeName(StrEnum):
    LOAD_TOPIC = "load_topic"
    RETRIEVE_BUSINESS_CONTEXT = "retrieve_business_context"
    EXPAND_QUERIES = "expand_queries"
    PLAN_SOURCES = "plan_sources"
    RETRIEVE_CANDIDATES = "retrieve_candidates"
    FETCH_CONTENTS = "fetch_contents"
    EXTRACT_STRUCTURED_ITEMS = "extract_structured_items"
    DEDUPLICATE_ITEMS = "deduplicate_items"
    SCORE_ITEMS = "score_items"
    DECIDE_PUSH = "decide_push"
    PERSIST_PUSH_RECORDS = "persist_push_records"
    NOTIFICATION_SEND = "notification_send"
    INDEX_HISTORY = "index_history"
    EVALUATE_RUN = "evaluate_run"


class EventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    run_id: str
    topic_id: str
    event_type: EventType
    node: MonitorNodeName
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    elapsed_ms: int | None = None
    created_at: datetime | None = None


class EventListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    events: list[EventRecord]
