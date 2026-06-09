from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.monitor import get_monitor_run_repository
from app.schemas.candidate_schema import CandidateItem, CandidateListResponse
from app.storage.repository import MonitorRunRepositoryProtocol

router = APIRouter(prefix="/api/monitor", tags=["candidates"])


def _to_candidate_payload(candidate: dict[str, Any]) -> CandidateItem:
    return CandidateItem.model_validate(
        {
            "candidate_id": candidate["candidate_id"],
            "run_id": candidate["run_id"],
            "topic_id": candidate["topic_id"],
            "source_type": candidate["source_type"],
            "source_name": candidate["source_name"],
            "title": candidate["title"],
            "url": candidate["url"],
            "published_at": candidate.get("published_at"),
            "raw_summary": candidate.get("raw_summary"),
            "fetch_status": candidate.get("fetch_status", "pending"),
        }
    )


@router.get("/runs/{run_id}/candidates", response_model=CandidateListResponse)
def list_candidates(
    run_id: str,
    repository: Annotated[
        MonitorRunRepositoryProtocol,
        Depends(get_monitor_run_repository),
    ],
) -> CandidateListResponse:
    run_record = repository.get_monitor_run(run_id)
    if run_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monitor run not found",
        )

    snapshot = dict(run_record.state_snapshot)
    return CandidateListResponse(
        run_id=run_id,
        candidates=[
            _to_candidate_payload(candidate)
            for candidate in snapshot.get("candidate_items", [])
        ],
    )
