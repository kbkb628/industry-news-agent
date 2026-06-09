from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.monitor import get_monitor_run_repository
from app.schemas.eval_schema import EvalResultResponse
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
