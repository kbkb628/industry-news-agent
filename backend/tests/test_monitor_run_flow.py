from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from threading import Event
import time
from typing import Callable, Iterator

from fastapi.testclient import TestClient

from app.api.monitor import get_monitor_graph, get_monitor_run_repository
from app.api.topics import get_topic_repository
from app.agent.graph import build_monitor_graph
from app.llm.mock_client import MockLLM
from app.main import create_app
from app.storage.repository import (
    MonitorRunRecord,
    MonitorRunUpsertData,
    TopicCreateData,
    TopicRecord,
)


def test_monitor_graph_runs_to_completion() -> None:
    class RecordingMonitorRunRepository:
        def __init__(self) -> None:
            self.monitor_runs: list[object] = []
            self.push_records: list[dict[str, object]] = []
            self.run_events: list[dict[str, object]] = []
            self.eval_results: list[dict[str, object]] = []

        def upsert_monitor_run(self, payload: object) -> object:
            self.monitor_runs.append(payload)
            return payload

        def list_push_history(self, topic_id: str) -> list[dict[str, object]]:
            assert topic_id == "topic_ai_agent"
            return []

        def create_push_records(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            persisted = [
                {
                    "push_id": f"push_{index + 1:03d}",
                    "run_id": payload.run_id,
                    "topic_id": payload.topic_id,
                    "candidate_id": payload.candidate_id,
                    "extracted_id": payload.extracted_id,
                    "title": payload.title,
                    "url": payload.url,
                    "summary": payload.summary,
                    "should_push": payload.should_push,
                    "score": payload.score,
                    "decision_reason": payload.decision_reason,
                    "pushed_at": payload.pushed_at,
                }
                for index, payload in enumerate(payloads)
            ]
            self.push_records.extend(persisted)
            return persisted

        def create_run_events(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            persisted = [
                {
                    "run_id": payload.run_id,
                    "topic_id": payload.topic_id,
                    "event_type": payload.event_type,
                    "node": payload.node,
                    "message": payload.message,
                    "payload": payload.payload,
                    "elapsed_ms": payload.elapsed_ms,
                    "created_at": datetime(2026, 6, 9, tzinfo=UTC),
                }
                for payload in payloads
            ]
            self.run_events.extend(persisted)
            return persisted

        def create_eval_result(self, payload: object) -> dict[str, object]:
            persisted = {
                "eval_id": "eval_001",
                "run_id": payload.run_id,
                "topic_id": payload.topic_id,
                "retrieved_count": payload.retrieved_count,
                "deduped_count": payload.deduped_count,
                "dedup_rate": payload.dedup_rate,
                "push_count": payload.push_count,
                "duplicate_push_count": payload.duplicate_push_count,
                "tool_success_rate": payload.tool_success_rate,
                "fetch_success_rate": payload.fetch_success_rate,
                "trace_completeness": payload.trace_completeness,
                "suggestions": list(payload.suggestions),
                "created_at": datetime(2026, 6, 9, tzinfo=UTC),
            }
            self.eval_results.append(persisted)
            return persisted

    repository = RecordingMonitorRunRepository()
    graph = build_monitor_graph(llm=MockLLM(), run_repository=repository)

    result = graph.invoke(
        {
            "run_id": "run_task7_monitor",
            "topic_id": "topic_ai_agent",
            "topic": {
                "topic_id": "topic_ai_agent",
                "name": "AI Agent",
                "description": "Track enterprise AI agent launches and deployment updates.",
                "seed_keywords": ["OpenAI", "enterprise", "automation"],
                "trusted_sources": ["AI Daily RSS", "AI Search"],
                "exclude_keywords": ["rumor"],
                "push_threshold": 0.72,
                "cooldown_hours": 24,
                "enabled": True,
            },
            "seed_keywords": ["OpenAI", "enterprise", "automation"],
            "expanded_queries": [],
            "business_context": {},
            "source_plan": [],
            "candidate_items": [],
            "fetched_contents": [],
            "extracted_items": [],
            "deduped_items": [],
            "scored_items": [],
            "final_decisions": [],
            "decision_reasons": [],
            "push_records": [],
            "push_history": [],
            "tool_results": [],
            "eval_result": {},
            "events": [],
            "errors": [],
            "status": "created",
        }
    )

    assert result["status"] == "completed"
    assert result["expanded_queries"]
    assert len(result["candidate_items"]) == 3
    assert len(result["deduped_items"]) == 2
    assert len(result["scored_items"]) == 2
    assert len(result["final_decisions"]) == 2
    assert len(result["push_records"]) == 1
    assert result["decision_reasons"]
    assert result["eval_result"]["push_count"] == 1
    assert any(event["node"] == "decide_push" for event in result["events"])
    assert len(repository.monitor_runs) == 2
    assert len(repository.push_records) == 1
    assert repository.push_records[0]["title"]
    assert repository.push_records[0]["url"]
    assert repository.push_records[0]["pushed_at"] is not None
    assert len(repository.run_events) == len(result["events"])
    assert len(repository.eval_results) == 1


class InMemoryTopicRepository:
    def __init__(self) -> None:
        self._records: list[TopicRecord] = []

    def create_topic(self, payload: TopicCreateData) -> TopicRecord:
        timestamp = datetime(2026, 6, 9, tzinfo=UTC)
        record = TopicRecord(
            topic_id=(
                "topic_ai_agent"
                if not self._records and payload.name == "AI Agent"
                else f"topic_{len(self._records) + 1:03d}"
            ),
            name=payload.name,
            description=payload.description,
            seed_keywords=payload.seed_keywords,
            trusted_sources=payload.trusted_sources,
            exclude_keywords=payload.exclude_keywords,
            push_threshold=payload.push_threshold,
            cooldown_hours=payload.cooldown_hours,
            enabled=payload.enabled,
            schedule_cron=payload.schedule_cron,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._records.append(record)
        return record

    def list_topics(self) -> list[TopicRecord]:
        return list(self._records)

    def get_topic(self, topic_id: str) -> TopicRecord | None:
        for record in self._records:
            if record.topic_id == topic_id:
                return record
        return None


class InMemoryMonitorRunRepository:
    def __init__(self) -> None:
        self._created_at = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
        self.monitor_runs: dict[str, MonitorRunRecord] = {}
        self.push_records: list[dict[str, object]] = []
        self.run_events: list[dict[str, object]] = []
        self.eval_results: dict[str, dict[str, object]] = {}

    def upsert_monitor_run(self, payload: object) -> MonitorRunRecord:
        existing = self.monitor_runs.get(payload.run_id)
        record = MonitorRunRecord(
            run_id=payload.run_id,
            topic_id=payload.topic_id,
            status=payload.status,
            state_snapshot=dict(payload.state_snapshot),
            error_summary=payload.error_summary,
            started_at=payload.started_at or (existing.started_at if existing else self._created_at),
            finished_at=payload.finished_at or (
                self._created_at if payload.status == "completed" else (existing.finished_at if existing else None)
            ),
            created_at=existing.created_at if existing else self._created_at,
        )
        self.monitor_runs[payload.run_id] = record
        return record

    def get_monitor_run(self, run_id: str) -> MonitorRunRecord | None:
        return self.monitor_runs.get(run_id)

    def list_push_history(self, topic_id: str) -> list[dict[str, object]]:
        return [
            push
            for push in self.push_records
            if push["topic_id"] == topic_id and push["should_push"] is True
        ]

    def list_push_records(
        self,
        *,
        topic_id: str | None = None,
        run_id: str | None = None,
    ) -> list[dict[str, object]]:
        records = list(self.push_records)
        if topic_id is not None:
            records = [record for record in records if record["topic_id"] == topic_id]
        if run_id is not None:
            records = [record for record in records if record["run_id"] == run_id]
        return records

    def create_push_records(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
        persisted = [
            {
                "push_id": f"push_{len(self.push_records) + index + 1:03d}",
                "run_id": payload.run_id,
                "topic_id": payload.topic_id,
                "candidate_id": payload.candidate_id,
                "extracted_id": payload.extracted_id,
                "title": payload.title,
                "url": payload.url,
                "summary": payload.summary,
                "should_push": payload.should_push,
                "score": payload.score,
                "decision_reason": payload.decision_reason,
                "pushed_at": payload.pushed_at,
            }
            for index, payload in enumerate(payloads)
        ]
        self.push_records.extend(persisted)
        return persisted

    def list_run_events(self, run_id: str) -> list[dict[str, object]]:
        return [event for event in self.run_events if event["run_id"] == run_id]

    def create_run_events(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
        persisted = [
            {
                "event_id": f"evt_{len(self.run_events) + index + 1:03d}",
                "run_id": payload.run_id,
                "topic_id": payload.topic_id,
                "event_type": payload.event_type,
                "node": payload.node,
                "message": payload.message,
                "payload": payload.payload,
                "elapsed_ms": payload.elapsed_ms,
                "created_at": self._created_at,
            }
            for index, payload in enumerate(payloads)
        ]
        self.run_events.extend(persisted)
        return persisted

    def get_eval_result(self, run_id: str | None = None) -> dict[str, object] | None:
        if run_id is not None:
            return self.eval_results.get(run_id)
        if not self.eval_results:
            return None
        latest_run_id = sorted(self.eval_results.keys())[-1]
        return self.eval_results[latest_run_id]

    def create_eval_result(self, payload: object) -> dict[str, object]:
        persisted = {
            "eval_id": f"eval_{len(self.eval_results) + 1:03d}",
            "run_id": payload.run_id,
            "topic_id": payload.topic_id,
            "retrieved_count": payload.retrieved_count,
            "deduped_count": payload.deduped_count,
            "dedup_rate": payload.dedup_rate,
            "push_count": payload.push_count,
            "duplicate_push_count": payload.duplicate_push_count,
            "tool_success_rate": payload.tool_success_rate,
            "fetch_success_rate": payload.fetch_success_rate,
            "trace_completeness": payload.trace_completeness,
            "suggestions": list(payload.suggestions),
            "created_at": self._created_at,
        }
        self.eval_results[payload.run_id] = persisted
        return persisted


@contextmanager
def _build_monitor_client(
    topic_repository: InMemoryTopicRepository,
    run_repository: InMemoryMonitorRunRepository,
    graph: object | None = None,
) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_topic_repository] = lambda: topic_repository
    app.dependency_overrides[get_monitor_run_repository] = lambda: run_repository
    if graph is not None:
        app.dependency_overrides[get_monitor_graph] = lambda: graph
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _create_monitor_topic(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/topics",
        json={
            "name": "AI Agent",
            "description": "Track enterprise AI agent launches and deployment updates.",
            "seed_keywords": ["OpenAI", "enterprise", "automation"],
            "trusted_sources": ["AI Daily RSS", "AI Search"],
            "exclude_keywords": ["rumor"],
            "push_threshold": 0.72,
            "cooldown_hours": 24,
            "enabled": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def _wait_until(predicate: Callable[[], bool], timeout_seconds: float = 1.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for asynchronous monitor run state")


def test_run_monitor_endpoint_executes_full_flow() -> None:
    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()

    with _build_monitor_client(topic_repository, run_repository) as client:
        topic = _create_monitor_topic(client)
        response = client.post(f"/api/monitor/{topic['topic_id']}/run")
        run_id = response.json()["run_id"]
        _wait_until(
            lambda: run_repository.get_monitor_run(run_id) is not None
            and run_repository.get_monitor_run(run_id).status == "completed"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"].startswith("run_")
    assert payload["topic_id"] == topic["topic_id"]
    assert payload["status"] == "running"
    assert payload["started_at"] is not None
    assert payload["finished_at"] is None
    assert len(run_repository.push_records) == 1


def test_run_monitor_endpoint_returns_before_background_flow_finishes() -> None:
    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()
    started = Event()
    release = Event()

    class BlockingGraph:
        def invoke(self, state: dict[str, object]) -> dict[str, object]:
            started.set()
            assert release.wait(1.0)
            run_repository.upsert_monitor_run(
                MonitorRunUpsertData(
                    run_id=str(state["run_id"]),
                    topic_id=str(state["topic_id"]),
                    status="completed",
                    state_snapshot={**dict(state), "status": "completed"},
                    error_summary=None,
                    started_at=None,
                    finished_at=datetime(2026, 6, 9, 12, 5, tzinfo=UTC),
                )
            )
            return state

    with _build_monitor_client(
        topic_repository,
        run_repository,
        graph=BlockingGraph(),
    ) as client:
        topic = _create_monitor_topic(client)
        start_time = time.monotonic()
        response = client.post(f"/api/monitor/{topic['topic_id']}/run")
        elapsed = time.monotonic() - start_time
        payload = response.json()

        assert response.status_code == 200
        assert elapsed < 0.5
        assert payload["status"] == "running"
        assert started.wait(0.5)
        assert run_repository.get_monitor_run(payload["run_id"]).status == "running"

        release.set()
        _wait_until(
            lambda: run_repository.get_monitor_run(payload["run_id"]).status
            == "completed"
        )


def test_run_detail_returns_completed_state() -> None:
    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()

    with _build_monitor_client(topic_repository, run_repository) as client:
        topic = _create_monitor_topic(client)
        run_payload = client.post(f"/api/monitor/{topic['topic_id']}/run").json()
        _wait_until(
            lambda: run_repository.get_monitor_run(run_payload["run_id"]) is not None
            and run_repository.get_monitor_run(run_payload["run_id"]).status
            == "completed"
        )
        response = client.get(f"/api/monitor/runs/{run_payload['run_id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["expanded_queries"]
    assert len(payload["candidate_items"]) == 3
    assert len(payload["final_decisions"]) == 2
    assert payload["errors"] == []


def test_reporting_endpoints_return_persisted_monitor_artifacts() -> None:
    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()

    with _build_monitor_client(topic_repository, run_repository) as client:
        topic = _create_monitor_topic(client)
        run_payload = client.post(f"/api/monitor/{topic['topic_id']}/run").json()
        run_id = run_payload["run_id"]
        _wait_until(
            lambda: run_repository.get_monitor_run(run_id) is not None
            and run_repository.get_monitor_run(run_id).status == "completed"
        )

        candidates_response = client.get(f"/api/monitor/runs/{run_id}/candidates")
        pushes_response = client.get("/api/pushes")
        topic_pushes_response = client.get(f"/api/topics/{topic['topic_id']}/pushes")
        events_response = client.get(f"/api/monitor/runs/{run_id}/events")
        eval_response = client.post("/api/eval/run")

    assert candidates_response.status_code == 200
    assert len(candidates_response.json()["candidates"]) == 3
    assert pushes_response.status_code == 200
    assert len(pushes_response.json()["pushes"]) == 1
    assert topic_pushes_response.status_code == 200
    assert topic_pushes_response.json()["topic_id"] == topic["topic_id"]
    assert len(topic_pushes_response.json()["pushes"]) == 1
    assert events_response.status_code == 200
    assert len(events_response.json()["events"]) >= 10
    assert eval_response.status_code == 200
    assert eval_response.json()["run_id"] == run_id
    assert eval_response.json()["push_count"] == 1


def test_eval_run_route_does_not_expose_request_body_contract() -> None:
    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()

    with _build_monitor_client(topic_repository, run_repository) as client:
        schema = client.get("/openapi.json").json()

    eval_operation = schema["paths"]["/api/eval/run"]["post"]
    assert "requestBody" not in eval_operation
