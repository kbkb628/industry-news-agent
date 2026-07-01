from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from threading import Thread
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.agent.contracts import (
    build_empty_candidate_task_output,
    build_empty_evaluation_output,
    build_empty_extraction_output,
    build_empty_planner_output,
    build_empty_retrieval_output,
)
from app.agent.graph import build_monitor_graph
from app.core.config import Settings
from app.core.config import get_settings
from app.llm.mock_client import MockLLM
from app.schemas.monitor_schema import (
    CandidateTaskRecordListResponse,
    MonitorRunStateResponse,
    MonitorRunSummary,
)
from app.storage.database import get_db, get_session_factory
from app.storage.repository import (
    MonitorRunUpsertData,
    MonitorRunRepositoryProtocol,
    SqlAlchemyMonitorRunRepository,
    TopicRecord,
    TopicRepositoryProtocol,
    build_monitor_run_repository,
)
from app.api.topics import get_topic_repository

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


def _get_optional_settings() -> Settings | None:
    try:
        return get_settings()
    except ValidationError:
        return None


def get_monitor_run_repository(
    session: Annotated[Session, Depends(get_db)],
) -> MonitorRunRepositoryProtocol:
    return build_monitor_run_repository(session)


def get_monitor_graph(
    repository: Annotated[
        MonitorRunRepositoryProtocol,
        Depends(get_monitor_run_repository),
    ],
) -> CompiledStateGraph:
    return build_monitor_graph(
        llm=MockLLM(),
        run_repository=repository,
        settings=_get_optional_settings(),
    )


def _topic_to_graph_payload(topic: TopicRecord) -> dict[str, Any]:
    return {
        "topic_id": topic.topic_id,
        "name": topic.name,
        "description": topic.description,
        "seed_keywords": list(topic.seed_keywords),
        "trusted_sources": list(topic.trusted_sources),
        "exclude_keywords": list(topic.exclude_keywords),
        "push_threshold": topic.push_threshold,
        "cooldown_hours": topic.cooldown_hours,
        "enabled": topic.enabled,
        "schedule_cron": topic.schedule_cron,
    }


def _build_initial_state(topic: TopicRecord, run_id: str) -> dict[str, Any]:
    orchestration = build_empty_candidate_task_output()
    return {
        "run_id": run_id,
        "topic_id": topic.topic_id,
        "trigger": "manual",
        "topic": _topic_to_graph_payload(topic),
        "seed_keywords": list(topic.seed_keywords),
        "expanded_queries": [],
        "business_context": {},
        "source_plan": [],
        "candidate_items": [],
        "planner_output": build_empty_planner_output(),
        "retrieval_output": build_empty_retrieval_output(),
        "extraction_output": build_empty_extraction_output(),
        "evaluation_output": build_empty_evaluation_output(),
        "fetched_contents": [],
        "extracted_items": [],
        "deduped_items": [],
        "scored_items": [],
        "final_decisions": [],
        "decision_reasons": [],
        "candidate_task_plan": list(orchestration["tasks"]),
        "candidate_task_runtime": dict(orchestration["runtime"]),
        "candidate_task_summary": dict(orchestration["summary"]),
        "push_records": [],
        "push_history": [],
        "tool_results": [],
        "eval_result": {},
        "events": [],
        "errors": [],
        "status": "created",
    }


def _persist_initial_run(
    repository: MonitorRunRepositoryProtocol,
    initial_state: dict[str, Any],
) -> None:
    running_state = {
        **deepcopy(initial_state),
        "status": "running",
    }
    repository.upsert_monitor_run(
        MonitorRunUpsertData(
            run_id=str(running_state["run_id"]),
            topic_id=str(running_state["topic_id"]),
            status="running",
            state_snapshot=running_state,
            error_summary=None,
            started_at=datetime.now(UTC),
            finished_at=None,
        )
    )


def _mark_run_failed(
    repository: MonitorRunRepositoryProtocol,
    initial_state: dict[str, Any],
    exc: Exception,
) -> None:
    repository.upsert_monitor_run(
        MonitorRunUpsertData(
            run_id=str(initial_state["run_id"]),
            topic_id=str(initial_state["topic_id"]),
            status="failed",
            state_snapshot={
                **deepcopy(initial_state),
                "status": "failed",
                "errors": [{"message": str(exc)}],
            },
            error_summary=str(exc),
            started_at=None,
            finished_at=datetime.now(UTC),
        )
    )


def _invoke_graph(
    graph: CompiledStateGraph,
    initial_state: dict[str, Any],
    repository: MonitorRunRepositoryProtocol,
) -> None:
    try:
        graph.invoke(deepcopy(initial_state))
    except Exception as exc:
        _mark_run_failed(repository, initial_state, exc)


def _invoke_graph_with_fresh_session(initial_state: dict[str, Any]) -> None:
    session = get_session_factory()()
    repository = build_monitor_run_repository(session)
    try:
        graph = build_monitor_graph(
            llm=MockLLM(),
            run_repository=repository,
            settings=_get_optional_settings(),
        )
        graph.invoke(deepcopy(initial_state))
    except Exception as exc:
        _mark_run_failed(repository, initial_state, exc)
    finally:
        session.close()


def _start_background_run(
    graph: CompiledStateGraph,
    initial_state: dict[str, Any],
    repository: MonitorRunRepositoryProtocol,
) -> None:
    if isinstance(repository, SqlAlchemyMonitorRunRepository):
        target = lambda: _invoke_graph_with_fresh_session(initial_state)
    else:
        target = lambda: _invoke_graph(graph, initial_state, repository)
    Thread(target=target, daemon=True).start()


@router.post("/{topic_id}/run", response_model=MonitorRunSummary)
def run_monitor(
    topic_id: str,
    topic_repository: Annotated[
        TopicRepositoryProtocol,
        Depends(get_topic_repository),
    ],
    monitor_repository: Annotated[
        MonitorRunRepositoryProtocol,
        Depends(get_monitor_run_repository),
    ],
    graph: Annotated[CompiledStateGraph, Depends(get_monitor_graph)],
) -> MonitorRunSummary:
    topic = topic_repository.get_topic(topic_id)
    if topic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found",
        )
    active_run = monitor_repository.get_active_run_for_topic(topic_id)
    if active_run is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Monitor run already active for topic",
        )

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    initial_state = _build_initial_state(topic, run_id)
    _persist_initial_run(monitor_repository, initial_state)
    _start_background_run(graph, initial_state, monitor_repository)
    run_record = monitor_repository.get_monitor_run(run_id)
    if run_record is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Monitor run was not persisted",
        )

    return MonitorRunSummary(
        run_id=run_id,
        topic_id=topic.topic_id,
        trigger=str(initial_state["trigger"]),
        status="running",
        started_at=run_record.started_at,
        finished_at=None,
    )


@router.get("/runs/{run_id}", response_model=MonitorRunStateResponse)
def get_run_state(
    run_id: str,
    request: Request,
    repository: Annotated[
        MonitorRunRepositoryProtocol,
        Depends(get_monitor_run_repository),
    ],
) -> MonitorRunStateResponse:
    run_record = repository.get_monitor_run(run_id)
    if run_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monitor run not found",
    )

    snapshot = dict(run_record.state_snapshot)
    retry_state = None
    run_queue = getattr(request.app.state, "run_queue", None)
    if run_queue is not None and hasattr(run_queue, "get_retry_state"):
        retry_state = run_queue.get_retry_state(run_id)
    run_context = dict(snapshot.get("run_context", {}))
    if retry_state is not None:
        run_context["retry_state"] = retry_state
    return MonitorRunStateResponse(
        run_id=run_record.run_id,
        topic_id=run_record.topic_id,
        trigger=str(snapshot.get("trigger", "manual")),
        status=run_record.status,
        run_context=run_context,
        business_memory=dict(snapshot.get("business_memory", {})),
        planner_output=dict(snapshot.get("planner_output", {})),
        retrieval_output=dict(snapshot.get("retrieval_output", {})),
        extraction_output=dict(snapshot.get("extraction_output", {})),
        evaluation_output=dict(snapshot.get("evaluation_output", {})),
        history_index_result=dict(snapshot.get("history_index_result", {})),
        expanded_queries=list(snapshot.get("expanded_queries", [])),
        candidate_items=list(snapshot.get("candidate_items", [])),
        final_decisions=list(snapshot.get("final_decisions", [])),
        candidate_task_summary=dict(snapshot.get("candidate_task_summary", {})),
        integration_runtime=dict(snapshot.get("integration_runtime", {})),
        errors=list(snapshot.get("errors", [])),
        started_at=run_record.started_at,
        finished_at=run_record.finished_at,
    )


@router.get(
    "/runs/{run_id}/candidate-tasks",
    response_model=CandidateTaskRecordListResponse,
)
def list_run_candidate_tasks(
    run_id: str,
    candidate_id: str | None = None,
    repository: Annotated[
        MonitorRunRepositoryProtocol,
        Depends(get_monitor_run_repository),
    ] = None,
) -> CandidateTaskRecordListResponse:
    run_record = repository.get_monitor_run(run_id)
    if run_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monitor run not found",
        )

    items = repository.list_candidate_task_records(
        run_id,
        candidate_id=candidate_id,
    )
    return CandidateTaskRecordListResponse(items=items)
