from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.monitor import get_monitor_run_repository
from app.schemas.push_schema import PushListResponse, PushRecord as PushRecordResponse
from app.storage.repository import MonitorRunRepositoryProtocol

router = APIRouter(prefix="/api", tags=["pushes"])


def _to_push_record(push: dict[str, Any]) -> PushRecordResponse:
    return PushRecordResponse.model_validate(
        {
            "push_id": push["push_id"],
            "run_id": push["run_id"],
            "topic_id": push["topic_id"],
            "candidate_id": push["candidate_id"],
            "extracted_id": push.get("extracted_id"),
            "should_push": push["should_push"],
            "score": push["score"],
            "decision_reason": push.get("decision_reason"),
            "pushed_at": push.get("pushed_at"),
        }
    )


@router.get("/pushes", response_model=PushListResponse)
def list_pushes(
    repository: Annotated[
        MonitorRunRepositoryProtocol,
        Depends(get_monitor_run_repository),
    ],
) -> PushListResponse:
    pushes = repository.list_push_records()
    return PushListResponse(pushes=[_to_push_record(push) for push in pushes])


@router.get("/topics/{topic_id}/pushes", response_model=PushListResponse)
def list_topic_pushes(
    topic_id: str,
    repository: Annotated[
        MonitorRunRepositoryProtocol,
        Depends(get_monitor_run_repository),
    ],
) -> PushListResponse:
    pushes = repository.list_push_records(topic_id=topic_id)
    return PushListResponse(
        topic_id=topic_id,
        pushes=[_to_push_record(push) for push in pushes],
    )
