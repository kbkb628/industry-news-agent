from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.monitor import get_monitor_run_repository
from app.schemas.eval_schema import EvalResultResponse, EvalSummaryResponse
from app.storage.repository import MonitorRunRepositoryProtocol

router = APIRouter(prefix="/api/eval", tags=["eval"])


@router.post("/run", response_model=EvalResultResponse)
def run_eval(
    repository: Annotated[
        MonitorRunRepositoryProtocol,
        Depends(get_monitor_run_repository),
    ],
) -> EvalResultResponse:
    result = repository.get_eval_result()
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Eval result not found",
        )
    return EvalResultResponse.model_validate(result)


@router.get("/summary", response_model=EvalSummaryResponse)
def get_eval_summary(
    repository: Annotated[
        MonitorRunRepositoryProtocol,
        Depends(get_monitor_run_repository),
    ],
) -> EvalSummaryResponse:
    result = repository.get_eval_summary()
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Eval summary not found",
        )
    return EvalSummaryResponse.model_validate(result)
