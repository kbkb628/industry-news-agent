from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.history_schema import HistorySearchItem, HistorySearchResponse
from app.search.history_index import HistoryIndexProtocol, build_history_index

router = APIRouter(prefix="/api/history", tags=["history"])


def get_history_index() -> HistoryIndexProtocol:
    try:
        settings = get_settings()
    except ValidationError:
        settings = None
    return build_history_index(settings=settings)


def _to_history_item(item: dict[str, Any]) -> HistorySearchItem:
    return HistorySearchItem.model_validate(
        {
            "candidate_id": item.get("candidate_id", ""),
            "run_id": item.get("run_id", ""),
            "topic_id": item.get("topic_id", ""),
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "decision_reason": item.get("decision_reason"),
        }
    )


@router.get("/search", response_model=HistorySearchResponse)
def search_history(
    q: Annotated[str, Query(min_length=1)],
    top_k: Annotated[int, Query(ge=1, le=20)] = 5,
    exclude_run_id: str | None = None,
    history_index: Annotated[HistoryIndexProtocol, Depends(get_history_index)] = None,
) -> HistorySearchResponse:
    result = history_index.search_candidates(
        q,
        top_k=top_k,
        exclude_run_id=exclude_run_id,
        exclude_candidate_ids=None,
    )
    return HistorySearchResponse(
        provider=str(result.get("provider", "none")),
        query=q,
        top_k=top_k,
        exclude_run_id=exclude_run_id,
        items=[_to_history_item(item) for item in list(result.get("items", []))],
    )
