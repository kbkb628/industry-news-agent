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


def test_multi_agent_state_contract_sections_exist() -> None:
    from app.agent.contracts import (
        build_empty_business_memory,
        build_empty_evaluation_output,
        build_empty_extraction_output,
        build_empty_planner_output,
        build_empty_retrieval_output,
        build_empty_run_context,
    )

    run_context = build_empty_run_context(run_id="run_001", topic_id="topic_001")

    assert run_context["run_id"] == "run_001"
    assert run_context["topic_id"] == "topic_001"
    assert run_context["status"] == "created"
    assert build_empty_business_memory()["push_history"] == []
    assert build_empty_planner_output()["source_plan"] == []
    assert build_empty_retrieval_output()["candidate_pool"] == []
    assert build_empty_extraction_output()["evidence_items"] == []
    assert build_empty_evaluation_output()["final_decisions"] == []


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


def test_event_schema_accepts_notification_events() -> None:
    event = EventRecord(
        event_id="event_notification_001",
        run_id="run_001",
        topic_id="topic_001",
        event_type="notification_sent",
        node="notification_send",
        message="Sent webhook notification.",
        payload={"provider": "webhook", "sent_count": 1},
    )

    response = EventListResponse(run_id="run_001", events=[event])

    assert response.events[0].event_type == "notification_sent"
    assert response.events[0].node == "notification_send"


def test_event_schema_accepts_history_index_node() -> None:
    event = EventRecord(
        event_id="event_index_history_001",
        run_id="run_001",
        topic_id="topic_001",
        event_type="node_completed",
        node="index_history",
        message="Indexed pushed candidates into the history index.",
        payload={"provider": "opensearch", "indexed_count": 1},
    )

    response = EventListResponse(run_id="run_001", events=[event])

    assert response.events[0].event_type == "node_completed"
    assert response.events[0].node == "index_history"


@pytest.mark.parametrize(
    ("event_type", "node"),
    [
        ("queue_dequeued", "worker_dequeue"),
        ("governance_retry", "worker_retry"),
        ("governance_timeout", "worker_timeout"),
        ("governance_skipped", "worker_active_run_guard"),
        ("governance_failed", "worker_failed"),
    ],
)
def test_event_schema_accepts_worker_governance_events(
    event_type: str,
    node: str,
) -> None:
    event = EventRecord(
        event_id=f"event_{node}",
        run_id="run_001",
        topic_id="topic_001",
        event_type=event_type,
        node=node,
        message="Worker governance event.",
        payload={"queue_wait_ms": 12},
    )

    response = EventListResponse(run_id="run_001", events=[event])

    assert response.events[0].event_type == event_type
    assert response.events[0].node == node


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


def test_eval_schema_accepts_judge_fields() -> None:
    result = EvalResultResponse(
        eval_id="eval_judge_001",
        run_id="run_judge_001",
        topic_id="topic_001",
        retrieved_count=5,
        deduped_count=4,
        push_count=1,
        tool_success_rate=1.0,
        judge_mode="mock_rule_judge",
        judge_score=0.85,
        judge_reason="Mock judge found acceptable quality.",
        judge_issues=["fetch_degraded"],
    )

    assert result.judge_mode == "mock_rule_judge"
    assert result.judge_score == 0.85
    assert result.judge_issues == ["fetch_degraded"]
