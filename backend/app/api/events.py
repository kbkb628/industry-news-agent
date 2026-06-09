from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.monitor import get_monitor_run_repository
from app.schemas.event_schema import EventListResponse, EventRecord
from app.storage.repository import MonitorRunRepositoryProtocol

router = APIRouter(prefix="/api/monitor", tags=["events"])


def _to_event_record(event: dict[str, Any]) -> EventRecord:
    return EventRecord.model_validate(
        {
            "event_id": event["event_id"],
            "run_id": event["run_id"],
            "topic_id": event["topic_id"],
            "event_type": event["event_type"],
            "node": event["node"],
            "message": event["message"],
            "payload": event.get("payload", {}),
            "elapsed_ms": event.get("elapsed_ms"),
            "created_at": event.get("created_at"),
        }
    )


@router.get("/runs/{run_id}/events", response_model=EventListResponse)
def list_events(
    run_id: str,
    repository: Annotated[
        MonitorRunRepositoryProtocol,
        Depends(get_monitor_run_repository),
    ],
) -> EventListResponse:
    return EventListResponse(
        run_id=run_id,
        events=[
            _to_event_record(event)
            for event in repository.list_run_events(run_id)
        ],
    )
