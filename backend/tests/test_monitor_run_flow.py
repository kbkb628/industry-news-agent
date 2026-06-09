from __future__ import annotations

from datetime import UTC, datetime

from app.agent.graph import build_monitor_graph
from app.llm.mock_client import MockLLM


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
