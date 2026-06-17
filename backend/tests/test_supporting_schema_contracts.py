from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.candidate_schema import CandidateFetchStatus, CandidateItem, CandidateListResponse
from app.schemas.eval_schema import EvalResultResponse
from app.schemas.event_schema import EventListResponse, EventRecord, EventType
from app.schemas.monitor_schema import MonitorRunStateResponse, MonitorRunStatus, MonitorRunSummary
from app.schemas.push_schema import PushListResponse, PushRecord
from app.schemas.tool_schema import ToolError, ToolExecutionResult


def test_monitor_run_status_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        MonitorRunStateResponse(
            run_id="run_001",
            topic_id="topic_001",
            trigger="manual",
            status="unknown",
        )


def test_monitor_schema_defaults_and_summary_status() -> None:
    monitor = MonitorRunStateResponse(
        run_id="run_001",
        topic_id="topic_001",
        trigger="manual",
        status="completed",
    )
    summary = MonitorRunSummary(
        run_id=monitor.run_id,
        topic_id=monitor.topic_id,
        trigger=monitor.trigger,
        status="completed",
    )

    assert summary.status == "completed"
    assert summary.trigger == "manual"
    assert monitor.expanded_queries == []
    assert monitor.candidate_items == []
    assert monitor.final_decisions == []
    assert monitor.errors == []
    assert MonitorRunStatus.COMPLETED == "completed"


def test_candidate_fetch_status_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        CandidateItem(
            candidate_id="cand_001",
            run_id="run_001",
            topic_id="topic_001",
            source_type="rss",
            source_name="GitHub Blog",
            title="New AI Agent SDK",
            url="https://example.com/news",
            fetch_status="done",
        )


def test_candidate_list_response_uses_constrained_status() -> None:
    candidate = CandidateItem(
        candidate_id="cand_001",
        run_id="run_001",
        topic_id="topic_001",
        source_type="rss",
        source_name="GitHub Blog",
        title="New AI Agent SDK",
        url="https://example.com/news",
        fetch_status="fetched",
    )

    response = CandidateListResponse(run_id="run_001", candidates=[candidate])

    assert response.candidates[0].fetch_status == "fetched"
    assert CandidateFetchStatus.FETCHED == "fetched"


def test_push_list_response_keeps_push_records_focused() -> None:
    push = PushRecord(
        push_id="push_001",
        run_id="run_001",
        topic_id="topic_001",
        candidate_id="cand_001",
        should_push=True,
        score=0.91,
    )

    response = PushListResponse(topic_id="topic_001", pushes=[push])

    assert response.pushes[0].should_push is True
    assert response.pushes[0].score == 0.91


def test_event_type_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        EventRecord(
            event_id="event_001",
            run_id="run_001",
            topic_id="topic_001",
            event_type="custom",
            node="retrieve_candidates",
            message="Candidates retrieved",
        )


def test_event_list_response_uses_constrained_event_type() -> None:
    event = EventRecord(
        event_id="event_001",
        run_id="run_001",
        topic_id="topic_001",
        event_type="node_completed",
        node="retrieve_candidates",
        message="Candidates retrieved",
    )

    response = EventListResponse(run_id="run_001", events=[event])

    assert response.events[0].event_type == "node_completed"
    assert EventType.NODE_COMPLETED == "node_completed"


def test_tool_execution_result_carries_error_contract() -> None:
    result = ToolExecutionResult(
        success=False,
        tool_name="rss_tool",
        summary="RSS fallback applied",
        error=ToolError(code="timeout", message="Timed out", fallback="cached_feed"),
    )

    assert result.error is not None
    assert result.error.code == "timeout"


def test_eval_result_response_keeps_minimum_metrics_contract() -> None:
    timestamp = datetime(2026, 6, 9, tzinfo=UTC)
    result = EvalResultResponse(
        eval_id="eval_001",
        run_id="run_001",
        topic_id="topic_001",
        retrieved_count=12,
        deduped_count=9,
        push_count=2,
        tool_success_rate=0.75,
        raw_summary_count=4,
        browser_fallback_count=1,
        provider_fallback_count=2,
        created_at=timestamp,
    )

    assert result.retrieved_count == 12
    assert result.push_count == 2
    assert result.raw_summary_count == 4
    assert result.created_at == timestamp
