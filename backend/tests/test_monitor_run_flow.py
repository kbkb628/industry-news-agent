from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from threading import Event
import time
from typing import Callable, Iterator

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi.testclient import TestClient

from app.api.monitor import get_monitor_graph, get_monitor_run_repository
from app.api.topics import get_topic_repository
from app.agent.graph import build_monitor_graph
from app.llm.mock_client import MockLLM
from app.main import create_app
from app.mcp.local_gateway import LocalToolGateway
from app.scheduler.jobs import TopicSchedulerService
from app.scheduler.worker import InMemoryRunQueue, MonitorWorkerLoop, MonitorWorkerService, RunQueueMessage
from app.storage.repository import (
    MonitorRunRecord,
    MonitorRunUpsertData,
    TopicCreateData,
    TopicRecord,
)
from app.tools.responses import ToolResponse


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
    assert result["business_context"]["retrieval_mode"] == "hybrid_keyword_bm25"
    assert "keyword" in result["business_context"]["retrievers"]
    assert "bm25" in result["business_context"]["retrievers"]
    assert all(
        "retrievers" in document
        for document in result["business_context"]["documents"]
    )
    assert len(repository.monitor_runs) == 2
    assert len(repository.push_records) == 1
    assert repository.push_records[0]["title"]
    assert repository.push_records[0]["url"]
    assert repository.push_records[0]["pushed_at"] is not None
    assert len(repository.run_events) == len(result["events"])
    assert len(repository.eval_results) == 1


def test_monitor_graph_records_provider_and_browser_fallback_events() -> None:
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
            return []

        def create_push_records(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            return []

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

    def fallback_search_tool(run_id: str, topic: dict[str, object]) -> object:
        return ToolResponse.success(
            tool_name="search_news",
            summary="Used mock search fallback.",
            data={"run_id": run_id, "candidates": []},
            metadata={
                "provider": "open_websearch",
                "fallback_provider": "mock_search",
                "used_fallback": True,
            },
        )

    def browser_fetch_tool(candidates: list[dict[str, object]]) -> object:
        return ToolResponse.success(
            tool_name="fetch_article_content",
            summary="Fetched through browser fallback.",
            data={"candidates": []},
            metadata={"used_browser_fallback": True},
        )

    gateway = LocalToolGateway()
    gateway.register("rss_fetch", lambda run_id, topic: ToolResponse.success(
        tool_name="rss_fetch",
        summary="No RSS candidates.",
        data={"run_id": run_id, "candidates": []},
    ))
    gateway.register("mock_search", fallback_search_tool)
    gateway.register("fetch_article_content", browser_fetch_tool)
    gateway.register("extract_article", lambda run_id, topic, candidates: ToolResponse.success(
        tool_name="extract_article",
        summary="No articles.",
        data={"articles": [], "skipped_candidate_ids": []},
    ))
    gateway.register("deduplicate_items", lambda articles: ToolResponse.success(
        tool_name="deduplicate_items",
        summary="No deduped articles.",
        data={"articles": [], "deduped_count": 0, "dropped_candidate_ids": []},
    ))
    gateway.register("score_candidate", lambda topic, articles: ToolResponse.success(
        tool_name="score_candidate",
        summary="No scored articles.",
        data={"articles": []},
    ))
    gateway.register("decide_push", lambda run_id, topic, articles, push_history: ToolResponse.success(
        tool_name="decide_push",
        summary="No push decisions.",
        data={"pushes": [], "push_count": 0},
    ))

    graph = build_monitor_graph(
        llm=MockLLM(),
        gateway=gateway,
        run_repository=repository,
    )

    result = graph.invoke(
        {
            "run_id": "run_phase2c_provider_events",
            "topic_id": "topic_ai_agent",
            "topic": {
                "topic_id": "topic_ai_agent",
                "name": "AI Agent",
                "description": "Track enterprise AI agent launches.",
                "seed_keywords": ["OpenAI", "enterprise"],
                "trusted_sources": ["AI Search"],
                "exclude_keywords": [],
                "push_threshold": 0.72,
                "cooldown_hours": 24,
                "enabled": True,
            },
            "seed_keywords": ["OpenAI", "enterprise"],
            "expanded_queries": [],
            "business_context": {},
            "source_plan": ["rss_fetch", "mock_search"],
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
    provider_event = next(
        event for event in repository.run_events
        if event["event_type"] == "fallback_used"
        and event["node"] == "retrieve_candidates"
    )
    browser_event = next(
        event for event in repository.run_events
        if event["event_type"] == "fallback_used"
        and event["node"] == "fetch_contents"
    )
    assert provider_event["payload"]["provider"] == "open_websearch"
    assert provider_event["payload"]["fallback_provider"] == "mock_search"
    assert browser_event["payload"]["fallback"] == "browser_fetch"


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

    def get_active_run_for_topic(self, topic_id: str) -> MonitorRunRecord | None:
        active_runs = [
            run
            for run in self.monitor_runs.values()
            if run.topic_id == topic_id and run.status == "running"
        ]
        if not active_runs:
            return None
        return sorted(
            active_runs,
            key=lambda run: (run.created_at, run.run_id),
            reverse=True,
        )[0]

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
    assert payload["trigger"] == "manual"
    assert payload["started_at"] is not None
    assert payload["finished_at"] is None
    assert len(run_repository.push_records) == 1
    persisted_run = run_repository.get_monitor_run(payload["run_id"])
    assert persisted_run is not None
    assert persisted_run.state_snapshot["trigger"] == "manual"


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
        assert payload["trigger"] == "manual"
        assert started.wait(0.5)
        assert run_repository.get_monitor_run(payload["run_id"]).status == "running"

        release.set()
        _wait_until(
            lambda: run_repository.get_monitor_run(payload["run_id"]).status
            == "completed"
        )


def test_run_monitor_rejects_duplicate_active_run_for_same_topic() -> None:
    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()
    active_run = MonitorRunRecord(
        run_id="run_active_001",
        topic_id="topic_ai_agent",
        status="running",
        state_snapshot={
            "run_id": "run_active_001",
            "topic_id": "topic_ai_agent",
            "trigger": "manual",
            "status": "running",
        },
        error_summary=None,
        started_at=datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
        finished_at=None,
        created_at=datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
    )
    run_repository.monitor_runs[active_run.run_id] = active_run

    with _build_monitor_client(topic_repository, run_repository) as client:
        topic = _create_monitor_topic(client)
        response = client.post(f"/api/monitor/{topic['topic_id']}/run")

    assert response.status_code == 409
    assert response.json()["detail"] == "Monitor run already active for topic"


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
    assert payload["trigger"] == "manual"
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


def test_mvp_closed_loop_end_to_end() -> None:
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

        run_response = client.get(f"/api/monitor/runs/{run_id}")
        candidate_response = client.get(f"/api/monitor/runs/{run_id}/candidates")
        event_response = client.get(f"/api/monitor/runs/{run_id}/events")
        push_response = client.get(f"/api/topics/{topic['topic_id']}/pushes")
        eval_response = client.post("/api/eval/run")

    assert run_payload["status"] == "running"
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "completed"
    assert candidate_response.status_code == 200
    assert candidate_response.json()["run_id"] == run_id
    assert candidate_response.json()["candidates"]
    assert event_response.status_code == 200
    assert event_response.json()["run_id"] == run_id
    assert event_response.json()["events"]
    assert push_response.status_code == 200
    assert push_response.json()["topic_id"] == topic["topic_id"]
    assert push_response.json()["pushes"]
    assert eval_response.status_code == 200
    assert eval_response.json()["run_id"] == run_id
    assert eval_response.json()["push_count"] >= 0


def test_eval_run_route_does_not_expose_request_body_contract() -> None:
    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()

    with _build_monitor_client(topic_repository, run_repository) as client:
        schema = client.get("/openapi.json").json()

    eval_operation = schema["paths"]["/api/eval/run"]["post"]
    assert "requestBody" not in eval_operation


def test_worker_consumes_enqueued_topic_run_and_persists_monitor_run() -> None:
    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()
    topic = topic_repository.create_topic(
        TopicCreateData(
            name="AI Agent",
            description="Track enterprise AI agent launches and deployment updates.",
            seed_keywords=("OpenAI", "enterprise", "automation"),
            trusted_sources=("AI Daily RSS", "AI Search"),
            exclude_keywords=("rumor",),
            push_threshold=0.72,
            cooldown_hours=24,
            enabled=True,
            schedule_cron="0 */6 * * *",
        )
    )
    queue = InMemoryRunQueue()
    worker = MonitorWorkerService(
        topic_repository=topic_repository,
        run_repository=run_repository,
        llm=MockLLM(),
        queue=queue,
    )

    queue.enqueue(
        RunQueueMessage(
            topic_id=topic.topic_id,
            trigger="scheduler",
        )
    )

    result = worker.process_next()

    assert result is not None
    assert result["topic_id"] == topic.topic_id
    assert result["trigger"] == "scheduler"
    assert result["status"] == "completed"
    run_record = run_repository.get_monitor_run(result["run_id"])
    assert run_record is not None
    assert run_record.status == "completed"
    assert run_record.state_snapshot["trigger"] == "scheduler"


def test_worker_skips_duplicate_active_run_for_same_topic() -> None:
    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()
    topic = topic_repository.create_topic(
        TopicCreateData(
            name="AI Agent",
            description="Track enterprise AI agent launches and deployment updates.",
            seed_keywords=("OpenAI", "enterprise", "automation"),
            trusted_sources=("AI Daily RSS", "AI Search"),
            exclude_keywords=("rumor",),
            push_threshold=0.72,
            cooldown_hours=24,
            enabled=True,
            schedule_cron="0 */6 * * *",
        )
    )
    active_run = MonitorRunRecord(
        run_id="run_active_001",
        topic_id=topic.topic_id,
        status="running",
        state_snapshot={
            "run_id": "run_active_001",
            "topic_id": topic.topic_id,
            "trigger": "scheduler",
            "status": "running",
        },
        error_summary=None,
        started_at=datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
        finished_at=None,
        created_at=datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
    )
    run_repository.monitor_runs[active_run.run_id] = active_run
    queue = InMemoryRunQueue()
    worker = MonitorWorkerService(
        topic_repository=topic_repository,
        run_repository=run_repository,
        llm=MockLLM(),
        queue=queue,
    )

    queue.enqueue(
        RunQueueMessage(
            topic_id=topic.topic_id,
            trigger="scheduler",
        )
    )

    result = worker.process_next()

    assert result is not None
    assert result["topic_id"] == topic.topic_id
    assert result["status"] == "skipped_active_run"
    assert len(run_repository.monitor_runs) == 1
    assert len(run_repository.run_events) == 1
    skip_event = run_repository.run_events[0]
    assert skip_event["event_type"] == "governance_skipped"
    assert skip_event["node"] == "worker_active_run_guard"
    assert skip_event["payload"]["active_run_id"] == active_run.run_id
    assert skip_event["payload"]["queue_wait_ms"] >= 0


def test_scheduler_job_enqueues_and_worker_processes_topic_run() -> None:
    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()
    queue = InMemoryRunQueue()
    worker = MonitorWorkerService(
        topic_repository=topic_repository,
        run_repository=run_repository,
        llm=MockLLM(),
        queue=queue,
    )
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)

    try:
        topic = topic_repository.create_topic(
            TopicCreateData(
                name="AI Agent",
                description="Track enterprise AI agent launches and deployment updates.",
                seed_keywords=("OpenAI", "enterprise", "automation"),
                trusted_sources=("AI Daily RSS", "AI Search"),
                exclude_keywords=("rumor",),
                push_threshold=0.72,
                cooldown_hours=24,
                enabled=True,
                schedule_cron="0 */6 * * *",
            )
        )
        topic_scheduler = TopicSchedulerService(
            scheduler=scheduler,
            queue=queue,
        )

        topic_scheduler.register_topic(
            topic_id=topic.topic_id,
            schedule_cron=topic.schedule_cron,
            enabled=topic.enabled,
        )

        job = scheduler.get_job(f"topic:{topic.topic_id}")
        assert job is not None

        enqueue_result = job.func(**job.kwargs)
        worker_result = worker.process_next()
    finally:
        scheduler.shutdown(wait=False)

    assert enqueue_result["status"] == "queued"
    assert worker_result is not None
    assert worker_result["topic_id"] == topic.topic_id
    assert worker_result["trigger"] == "scheduler"
    run_record = run_repository.get_monitor_run(worker_result["run_id"])
    assert run_record is not None
    assert run_record.status == "completed"
    assert run_record.state_snapshot["trigger"] == "scheduler"


def test_worker_loop_survives_processing_error_and_continues() -> None:
    queue = InMemoryRunQueue()
    stop_event = Event()

    class FailingWorkerLoop:
        def __init__(self) -> None:
            self.calls = 0
            self.completed = Event()

        def process_next(self) -> dict[str, object] | None:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("boom")
            self.completed.set()
            stop_event.set()
            return {"status": "completed"}

    loop = FailingWorkerLoop()

    worker_loop = MonitorWorkerLoop(
        queue=queue,
        session_factory=lambda: None,  # type: ignore[arg-type]
    )
    worker_loop.process_next = loop.process_next  # type: ignore[method-assign]

    worker_loop.run_forever(stop_event)

    assert loop.calls >= 2
    assert loop.completed.is_set()


def test_worker_persists_failed_run_when_graph_raises(
    monkeypatch,
) -> None:
    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()
    topic = topic_repository.create_topic(
        TopicCreateData(
            name="AI Agent",
            description="Track enterprise AI agent launches and deployment updates.",
            seed_keywords=("OpenAI", "enterprise", "automation"),
            trusted_sources=("AI Daily RSS", "AI Search"),
            exclude_keywords=("rumor",),
            push_threshold=0.72,
            cooldown_hours=24,
            enabled=True,
            schedule_cron="0 */6 * * *",
        )
    )
    queue = InMemoryRunQueue()
    queue.enqueue(
        RunQueueMessage(
            topic_id=topic.topic_id,
            trigger="scheduler",
        )
    )

    worker = MonitorWorkerService(
        topic_repository=topic_repository,
        run_repository=run_repository,
        llm=MockLLM(),
        queue=queue,
    )
    class FailingGraph:
        def invoke(self, state: dict[str, object]) -> dict[str, object]:
            raise RuntimeError("graph failed")

    monkeypatch.setattr(
        "app.scheduler.worker.build_monitor_graph",
        lambda llm, run_repository: FailingGraph(),
    )

    result = worker.process_next()

    assert result is not None
    assert result["status"] == "failed"
    run_record = run_repository.get_monitor_run(result["run_id"])
    assert run_record is not None
    assert run_record.status == "failed"
    assert run_record.state_snapshot["trigger"] == "scheduler"
    assert run_record.error_summary == "graph failed"


def test_worker_retries_once_before_marking_run_failed(monkeypatch) -> None:
    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()
    topic = topic_repository.create_topic(
        TopicCreateData(
            name="AI Agent",
            description="Track enterprise AI agent launches and deployment updates.",
            seed_keywords=("OpenAI", "enterprise", "automation"),
            trusted_sources=("AI Daily RSS", "AI Search"),
            exclude_keywords=("rumor",),
            push_threshold=0.72,
            cooldown_hours=24,
            enabled=True,
            schedule_cron="0 */6 * * *",
        )
    )
    queue = InMemoryRunQueue()
    queue.enqueue(
        RunQueueMessage(
            topic_id=topic.topic_id,
            trigger="scheduler",
        )
    )

    attempts = {"count": 0}

    class RetryGraph:
        def invoke(self, state: dict[str, object]) -> dict[str, object]:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("transient failure")
            return {**state, "status": "completed"}

    monkeypatch.setattr(
        "app.scheduler.worker.build_monitor_graph",
        lambda llm, run_repository: RetryGraph(),
    )

    worker = MonitorWorkerService(
        topic_repository=topic_repository,
        run_repository=run_repository,
        llm=MockLLM(),
        queue=queue,
        max_retries=1,
    )

    result = worker.process_next()

    assert result is not None
    assert result["status"] == "completed"
    assert result["retry_count"] == 1
    assert attempts["count"] == 2
    run_record = run_repository.get_monitor_run(result["run_id"])
    assert run_record is not None
    assert run_record.status == "running" or run_record.status == "completed"
    events = run_repository.list_run_events(result["run_id"])
    dequeue_event = next(event for event in events if event["node"] == "worker_dequeue")
    retry_event = next(event for event in events if event["node"] == "worker_retry")
    assert dequeue_event["payload"]["queue_wait_ms"] >= 0
    assert retry_event["event_type"] == "governance_retry"
    assert retry_event["payload"]["attempt"] == 1
    assert retry_event["payload"]["max_retries"] == 1
    assert retry_event["payload"]["error_message"] == "transient failure"


def test_worker_times_out_and_marks_failed_run(monkeypatch) -> None:
    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()
    topic = topic_repository.create_topic(
        TopicCreateData(
            name="AI Agent",
            description="Track enterprise AI agent launches and deployment updates.",
            seed_keywords=("OpenAI", "enterprise", "automation"),
            trusted_sources=("AI Daily RSS", "AI Search"),
            exclude_keywords=("rumor",),
            push_threshold=0.72,
            cooldown_hours=24,
            enabled=True,
            schedule_cron="0 */6 * * *",
        )
    )
    queue = InMemoryRunQueue()
    queue.enqueue(
        RunQueueMessage(
            topic_id=topic.topic_id,
            trigger="scheduler",
        )
    )

    class SlowGraph:
        def invoke(self, state: dict[str, object]) -> dict[str, object]:
            time.sleep(0.05)
            return {**state, "status": "completed"}

    monkeypatch.setattr(
        "app.scheduler.worker.build_monitor_graph",
        lambda llm, run_repository: SlowGraph(),
    )

    worker = MonitorWorkerService(
        topic_repository=topic_repository,
        run_repository=run_repository,
        llm=MockLLM(),
        queue=queue,
        max_retries=0,
        invocation_timeout_seconds=0.01,
    )

    result = worker.process_next()

    assert result is not None
    assert result["status"] == "failed"
    run_record = run_repository.get_monitor_run(result["run_id"])
    assert run_record is not None
    assert run_record.status == "failed"
    assert "timed out" in (run_record.error_summary or "")
    events = run_repository.list_run_events(result["run_id"])
    dequeue_event = next(event for event in events if event["node"] == "worker_dequeue")
    failure_event = next(event for event in events if event["node"] == "worker_timeout")
    assert dequeue_event["payload"]["queue_wait_ms"] >= 0
    assert failure_event["event_type"] == "governance_timeout"
    assert failure_event["payload"]["max_retries"] == 0
    assert failure_event["payload"]["attempt"] == 1
    assert "timed out" in failure_event["payload"]["error_message"]
