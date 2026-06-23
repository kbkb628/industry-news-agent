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
from app.agent.nodes import evaluate_run_node, persist_push_records_node, supervisor_finalize_node
from app.core.config import Settings
from app.llm.mock_client import MockLLM
from app.main import create_app
from app.mcp.local_gateway import LocalToolGateway
from app.scheduler.jobs import TopicSchedulerService
from app.scheduler.worker import (
    InMemoryRunQueue,
    MonitorWorkerLoop,
    MonitorWorkerService,
    RedisStreamRunQueue,
    RunQueueMessage,
    enqueue_topic_run,
)
from app.storage.repository import (
    MonitorRunRecord,
    MonitorRunUpsertData,
    TopicCreateData,
    TopicRecord,
)
from app.tools.responses import ToolResponse


def test_retrieval_agent_writes_candidate_pool_and_provider_fallbacks() -> None:
    from app.agent.retrieval_agent import RetrievalAgent

    gateway = LocalToolGateway()
    gateway.register(
        "mock_search",
        lambda run_id, topic: ToolResponse.success(
            tool_name="mock_search",
            summary="Used fallback provider.",
            data={
                "candidates": [
                    {
                        "candidate_id": "cand_001",
                        "run_id": run_id,
                        "topic_id": topic["topic_id"],
                        "source_type": "search",
                        "source_name": "Mock Search",
                        "title": "AI Agent funding update",
                        "url": "https://example.com/funding",
                        "fetch_status": "pending",
                    }
                ]
            },
            metadata={
                "provider": "open_websearch",
                "fallback_provider": "mock_search",
                "fallback_reason": "provider unavailable",
                "used_fallback": True,
            },
        ),
    )
    state = {
        "run_context": {"run_id": "run_001"},
        "topic": {"topic_id": "topic_001", "name": "AI Agent"},
        "planner_output": {
            "source_plan": [{"tool_name": "mock_search", "priority": 1}],
            "retrieval_strategy": {"mode": "rss_first"},
        },
        "retrieval_output": {},
        "tool_results": [],
        "errors": [],
        "events": [],
    }

    result = RetrievalAgent(gateway=gateway).run(state)

    assert result["retrieval_output"]["candidate_pool"][0]["candidate_id"] == "cand_001"
    assert result["retrieval_output"]["source_coverage"][0]["tool_name"] == "mock_search"
    assert result["retrieval_output"]["provider_fallbacks"][0]["fallback_provider"] == "mock_search"


def test_extraction_agent_writes_evidence_items_and_content_fallbacks() -> None:
    from app.agent.extraction_agent import ExtractionAgent

    gateway = LocalToolGateway()
    gateway.register(
        "fetch_article_content",
        lambda candidates: ToolResponse.success(
            tool_name="fetch_article_content",
            summary="Fetched with browser fallback.",
            data={
                "candidates": [
                    {
                        "candidate_id": "cand_001",
                        "run_id": "run_001",
                        "topic_id": "topic_001",
                        "title": "AI Agent funding update",
                        "url": "https://example.com/funding",
                        "fetch_status": "fetched",
                        "content": "Funding details.",
                        "raw_summary": "Funding summary.",
                    }
                ]
            },
            metadata={"used_browser_fallback": True},
        ),
    )
    gateway.register(
        "extract_article",
        lambda run_id, topic, candidates: ToolResponse.success(
            tool_name="extract_article",
            summary="Extracted evidence items.",
            data={
                "articles": [
                    {
                        "extracted_id": "ext_001",
                        "candidate_id": "cand_001",
                        "run_id": run_id,
                        "topic_id": topic["topic_id"],
                        "source_type": "search",
                        "source_name": "Mock Search",
                        "title": "AI Agent funding update",
                        "url": "https://example.com/funding",
                        "summary": "Funding summary.",
                        "content": "Funding details.",
                        "fetch_status": "fetched",
                        "extraction_mode": "structured",
                    }
                ]
            },
        ),
    )
    state = {
        "run_context": {"run_id": "run_001"},
        "topic": {"topic_id": "topic_001", "name": "AI Agent"},
        "retrieval_output": {
            "candidate_pool": [
                {
                    "candidate_id": "cand_001",
                    "run_id": "run_001",
                    "topic_id": "topic_001",
                    "title": "AI Agent funding update",
                    "url": "https://example.com/funding",
                    "fetch_status": "pending",
                    "raw_summary": "Funding summary.",
                }
            ]
        },
        "extraction_output": {},
        "tool_results": [],
        "errors": [],
        "events": [],
    }

    result = ExtractionAgent(gateway=gateway).run(state)

    assert result["extraction_output"]["fetched_contents"][0]["candidate_id"] == "cand_001"
    assert result["extraction_output"]["evidence_items"][0]["extracted_id"] == "ext_001"
    assert result["extraction_output"]["content_fallbacks"][0]["fallback"] == "browser_fetch"


def test_fetch_and_extract_nodes_preserve_stage_split() -> None:
    from app.agent.nodes import extract_structured_items_node, fetch_contents_node

    gateway = LocalToolGateway()
    gateway.register(
        "fetch_article_content",
        lambda candidates: ToolResponse.success(
            tool_name="fetch_article_content",
            summary="Fetched article content.",
            data={
                "candidates": [
                    {
                        "candidate_id": "cand_001",
                        "run_id": "run_001",
                        "topic_id": "topic_001",
                        "title": "AI Agent funding update",
                        "url": "https://example.com/funding",
                        "fetch_status": "fetched",
                        "content": "Funding details.",
                        "raw_summary": "Funding summary.",
                    }
                ]
            },
        ),
    )
    gateway.register(
        "extract_article",
        lambda run_id, topic, candidates: ToolResponse.success(
            tool_name="extract_article",
            summary="Extracted evidence items.",
            data={
                "articles": [
                    {
                        "extracted_id": "ext_001",
                        "candidate_id": "cand_001",
                        "run_id": run_id,
                        "topic_id": topic["topic_id"],
                        "source_type": "search",
                        "source_name": "Mock Search",
                        "title": "AI Agent funding update",
                        "url": "https://example.com/funding",
                        "summary": "Funding summary.",
                        "content": "Funding details.",
                        "fetch_status": "fetched",
                        "extraction_mode": "structured",
                    }
                ]
            },
        ),
    )
    state = {
        "run_id": "run_001",
        "topic_id": "topic_001",
        "topic": {"topic_id": "topic_001", "name": "AI Agent"},
        "candidate_items": [
            {
                "candidate_id": "cand_001",
                "run_id": "run_001",
                "topic_id": "topic_001",
                "title": "AI Agent funding update",
                "url": "https://example.com/funding",
                "fetch_status": "pending",
                "raw_summary": "Funding summary.",
            }
        ],
        "fetched_contents": [],
        "extracted_items": [],
        "tool_results": [],
        "errors": [],
        "events": [],
    }

    fetched_state = fetch_contents_node(state, gateway)

    assert fetched_state["fetched_contents"][0]["candidate_id"] == "cand_001"
    assert fetched_state["extracted_items"] == []

    extracted_state = extract_structured_items_node(fetched_state, gateway)

    assert extracted_state["extracted_items"][0]["extracted_id"] == "ext_001"


def test_evaluation_agent_writes_evaluation_output_and_legacy_fields() -> None:
    from app.agent.evaluation_agent import EvaluationAgent

    gateway = LocalToolGateway()
    gateway.register(
        "deduplicate_items",
        lambda articles: ToolResponse.success(
            tool_name="deduplicate_items",
            summary="Deduplicated articles.",
            data={"articles": list(articles), "dropped_candidate_ids": []},
        ),
    )
    gateway.register(
        "score_candidate",
        lambda topic, articles: ToolResponse.success(
            tool_name="score_candidate",
            summary="Scored articles.",
            data={
                "articles": [
                    {
                        **dict(article),
                        "score": 0.91,
                        "score_breakdown": "Above threshold.",
                    }
                    for article in articles
                ]
            },
        ),
    )
    gateway.register(
        "decide_push",
        lambda run_id, topic, articles, push_history: ToolResponse.success(
            tool_name="decide_push",
            summary="Calculated push decisions.",
            data={
                "pushes": [
                    {
                        **dict(article),
                        "run_id": run_id,
                        "topic_id": topic["topic_id"],
                        "should_push": True,
                        "decision_reason": "Above threshold",
                    }
                    for article in articles
                ],
                "push_count": len(articles),
            },
        ),
    )
    state = {
        "run_id": "run_001",
        "topic_id": "topic_001",
        "topic": {"topic_id": "topic_001", "name": "AI Agent"},
        "push_history": [],
        "extraction_output": {
            "evidence_items": [
                {
                    "extracted_id": "ext_001",
                    "candidate_id": "cand_001",
                    "run_id": "run_001",
                    "topic_id": "topic_001",
                    "source_type": "search",
                    "source_name": "Mock Search",
                    "title": "AI Agent funding update",
                    "url": "https://example.com/funding",
                    "summary": "Funding summary.",
                }
            ]
        },
        "evaluation_output": {},
        "tool_results": [],
        "errors": [],
        "events": [],
    }

    result = EvaluationAgent(gateway=gateway).run(state)

    assert result["evaluation_output"]["final_decisions"][0]["candidate_id"] == "cand_001"
    assert result["evaluation_output"]["eval_result"]["push_count"] == 1
    assert result["final_decisions"] == result["evaluation_output"]["final_decisions"]
    assert result["eval_result"] == result["evaluation_output"]["eval_result"]


def test_supervisor_finalize_mirrors_structured_outputs_to_legacy_fields() -> None:
    from app.agent.nodes import supervisor_finalize_node

    state = {
        "run_id": "run_001",
        "topic_id": "topic_001",
        "retrieval_output": {
            "candidate_pool": [{"candidate_id": "cand_001"}],
        },
        "extraction_output": {
            "fetched_contents": [{"candidate_id": "cand_001"}],
            "evidence_items": [{"extracted_id": "ext_001", "candidate_id": "cand_001"}],
        },
        "evaluation_output": {
            "deduped_items": [{"candidate_id": "cand_001"}],
            "scored_items": [{"candidate_id": "cand_001", "score": 0.91}],
            "final_decisions": [{"candidate_id": "cand_001", "should_push": True}],
            "decision_reasons": ["Above threshold"],
            "push_records": [{"push_id": "push_001"}],
            "eval_result": {"push_count": 1},
        },
        "events": [],
        "errors": [],
        "tool_results": [],
        "status": "running",
    }

    result = supervisor_finalize_node(state)

    assert result["candidate_items"] == result["retrieval_output"]["candidate_pool"]
    assert result["fetched_contents"] == result["extraction_output"]["fetched_contents"]
    assert result["extracted_items"] == result["extraction_output"]["evidence_items"]
    assert result["final_decisions"] == result["evaluation_output"]["final_decisions"]
    assert result["eval_result"] == result["evaluation_output"]["eval_result"]


def test_build_monitor_graph_uses_stage_level_multi_agent_nodes() -> None:
    from app.agent.graph import build_monitor_graph

    graph = build_monitor_graph(llm=MockLLM())

    node_names = set(graph.get_graph().nodes.keys())

    assert "supervisor_bootstrap" in node_names
    assert "planner_agent" in node_names
    assert "retrieval_agent" in node_names
    assert "extraction_agent" in node_names
    assert "evaluation_agent" in node_names
    assert "supervisor_finalize" in node_names


def test_stage_level_graph_preserves_legacy_trace_nodes() -> None:
    class RecordingMonitorRunRepository:
        def __init__(self) -> None:
            self.monitor_runs: list[object] = []
            self.candidate_records: list[dict[str, object]] = []
            self.extracted_records: list[dict[str, object]] = []
            self.decision_records: list[dict[str, object]] = []
            self.push_records: list[dict[str, object]] = []
            self.run_events: list[dict[str, object]] = []
            self.eval_results: list[dict[str, object]] = []

        def upsert_monitor_run(self, payload: object) -> object:
            self.monitor_runs.append(payload)
            return payload

        def list_push_history(self, topic_id: str) -> list[dict[str, object]]:
            return []

        def create_push_records(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
            persisted = [{"push_id": "push_001"} for _ in payloads]
            self.push_records.extend(persisted)
            return persisted

        def upsert_candidate_records(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
            return []

        def list_candidate_records(self, run_id: str) -> list[dict[str, object]]:
            return []

        def upsert_extracted_item_records(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
            return []

        def list_extracted_item_records(self, run_id: str) -> list[dict[str, object]]:
            return []

        def upsert_decision_records(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
            return []

        def list_decision_records(self, run_id: str) -> list[dict[str, object]]:
            return []

        def create_run_events(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
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
            persisted = {"eval_id": "eval_001", "run_id": payload.run_id, "topic_id": payload.topic_id, "push_count": payload.push_count, "created_at": datetime(2026, 6, 9, tzinfo=UTC)}
            self.eval_results.append(persisted)
            return persisted

    repository = RecordingMonitorRunRepository()
    graph = build_monitor_graph(llm=MockLLM(), run_repository=repository)

    result = graph.invoke(
        {
            "run_id": "run_trace_nodes",
            "topic_id": "topic_ai_agent",
            "topic": {
                "topic_id": "topic_ai_agent",
                "name": "AI Agent",
                "description": "Track enterprise AI agent launches.",
                "seed_keywords": ["OpenAI", "enterprise"],
                "trusted_sources": ["AI Daily RSS", "AI Search"],
                "exclude_keywords": [],
                "push_threshold": 0.72,
                "cooldown_hours": 24,
                "enabled": True,
            },
            "seed_keywords": ["OpenAI", "enterprise"],
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

    observed_nodes = {event["node"] for event in result["events"]}
    assert "expand_queries" in observed_nodes
    assert "plan_sources" in observed_nodes
    assert "retrieve_candidates" in observed_nodes
    assert "fetch_contents" in observed_nodes
    assert "extract_structured_items" in observed_nodes


def test_monitor_graph_runs_to_completion() -> None:
    class RecordingMonitorRunRepository:
        def __init__(self) -> None:
            self.monitor_runs: list[object] = []
            self.candidate_records: list[dict[str, object]] = []
            self.extracted_records: list[dict[str, object]] = []
            self.decision_records: list[dict[str, object]] = []
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

        def upsert_candidate_records(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            persisted = [
                {
                    "candidate_id": payload.candidate_id,
                    "run_id": payload.run_id,
                    "topic_id": payload.topic_id,
                    "source_type": payload.source_type,
                    "source_name": payload.source_name,
                    "title": payload.title,
                    "url": payload.url,
                    "published_at": payload.published_at,
                    "raw_summary": payload.raw_summary,
                    "fetch_status": payload.fetch_status,
                    "content": payload.content,
                    "structured_payload": payload.structured_payload,
                    "score": payload.score,
                    "decision": payload.decision,
                    "decision_reason": payload.decision_reason,
                    "created_at": datetime(2026, 6, 9, tzinfo=UTC),
                }
                for payload in payloads
            ]
            self.candidate_records.extend(persisted)
            return persisted

        def list_candidate_records(self, run_id: str) -> list[dict[str, object]]:
            return [
                record
                for record in self.candidate_records
                if record["run_id"] == run_id
            ]

        def upsert_extracted_item_records(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            persisted = [
                {
                    "extracted_id": payload.extracted_id,
                    "run_id": payload.run_id,
                    "topic_id": payload.topic_id,
                    "candidate_id": payload.candidate_id,
                    "source_type": payload.source_type,
                    "source_name": payload.source_name,
                    "title": payload.title,
                    "url": payload.url,
                    "published_at": payload.published_at,
                    "summary": payload.summary,
                    "keywords": list(payload.keywords),
                    "content": payload.content,
                    "content_fingerprint": payload.content_fingerprint,
                    "fetch_status": payload.fetch_status,
                    "fetch_error": payload.fetch_error,
                    "extraction_mode": payload.extraction_mode,
                    "structured_payload": payload.structured_payload,
                    "created_at": datetime(2026, 6, 9, tzinfo=UTC),
                }
                for payload in payloads
            ]
            self.extracted_records.extend(persisted)
            return persisted

        def list_extracted_item_records(self, run_id: str) -> list[dict[str, object]]:
            return [
                record
                for record in self.extracted_records
                if record["run_id"] == run_id
            ]

        def upsert_decision_records(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            persisted = [
                {
                    "decision_id": payload.decision_id,
                    "run_id": payload.run_id,
                    "topic_id": payload.topic_id,
                    "candidate_id": payload.candidate_id,
                    "extracted_id": payload.extracted_id,
                    "source_type": payload.source_type,
                    "source_name": payload.source_name,
                    "title": payload.title,
                    "url": payload.url,
                    "published_at": payload.published_at,
                    "summary": payload.summary,
                    "score": payload.score,
                    "should_push": payload.should_push,
                    "decision_reason": payload.decision_reason,
                    "decision_payload": payload.decision_payload,
                    "created_at": datetime(2026, 6, 9, tzinfo=UTC),
                }
                for payload in payloads
            ]
            self.decision_records.extend(persisted)
            return persisted

        def list_decision_records(self, run_id: str) -> list[dict[str, object]]:
            return [
                record
                for record in self.decision_records
                if record["run_id"] == run_id
            ]

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
                "raw_summary_count": payload.raw_summary_count,
                "browser_fallback_count": payload.browser_fallback_count,
                "provider_fallback_count": payload.provider_fallback_count,
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
    assert len(result["extracted_items"]) == 3
    assert len(result["deduped_items"]) == 2
    assert len(result["scored_items"]) == 2
    assert len(result["final_decisions"]) == 2
    assert len(result["push_records"]) == 1
    assert result["decision_reasons"]
    assert result["eval_result"]["push_count"] == 1
    assert any(event["node"] == "decide_push" for event in result["events"])
    notification_event = next(
        event for event in result["events"] if event["node"] == "notification_send"
    )
    assert notification_event["event_type"] == "notification_skipped"
    assert notification_event["payload"]["provider"] == "none"
    assert result["business_context"]["retrieval_mode"] == (
        "hybrid_keyword_bm25_embedding_rerank"
    )
    assert "keyword" in result["business_context"]["retrievers"]
    assert "bm25" in result["business_context"]["retrievers"]
    assert "embedding_like" in result["business_context"]["retrievers"]
    assert all(
        "retrievers" in document and "rerank_score" in document
        for document in result["business_context"]["documents"]
    )
    assert len(repository.monitor_runs) == 2
    assert len(repository.push_records) == 1
    assert len(repository.extracted_records) == 3
    assert len(repository.decision_records) == 2
    assert repository.push_records[0]["title"]
    assert repository.push_records[0]["url"]
    assert repository.push_records[0]["pushed_at"] is not None
    assert len(repository.candidate_records) == 3
    assert len(repository.run_events) == len(result["events"])
    assert len(repository.eval_results) == 1


def test_monitor_graph_records_provider_and_browser_fallback_events() -> None:
    class RecordingMonitorRunRepository:
        def __init__(self) -> None:
            self.monitor_runs: list[object] = []
            self.candidate_records: list[dict[str, object]] = []
            self.extracted_records: list[dict[str, object]] = []
            self.decision_records: list[dict[str, object]] = []
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

        def upsert_candidate_records(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            return []

        def list_candidate_records(self, run_id: str) -> list[dict[str, object]]:
            return []

        def upsert_extracted_item_records(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            return []

        def list_extracted_item_records(self, run_id: str) -> list[dict[str, object]]:
            return []

        def upsert_decision_records(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            return []

        def list_decision_records(self, run_id: str) -> list[dict[str, object]]:
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
                "raw_summary_count": payload.raw_summary_count,
                "browser_fallback_count": payload.browser_fallback_count,
                "provider_fallback_count": payload.provider_fallback_count,
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


def test_monitor_graph_records_onesearch_provider_fallback_event() -> None:
    class RecordingMonitorRunRepository:
        def __init__(self) -> None:
            self.monitor_runs: list[object] = []
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

        def upsert_candidate_records(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            return []

        def list_candidate_records(self, run_id: str) -> list[dict[str, object]]:
            return []

        def upsert_extracted_item_records(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            return []

        def list_extracted_item_records(self, run_id: str) -> list[dict[str, object]]:
            return []

        def upsert_decision_records(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            return []

        def list_decision_records(self, run_id: str) -> list[dict[str, object]]:
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
                "raw_summary_count": payload.raw_summary_count,
                "browser_fallback_count": payload.browser_fallback_count,
                "provider_fallback_count": payload.provider_fallback_count,
                "judge_mode": payload.judge_mode,
                "judge_score": payload.judge_score,
                "judge_reason": payload.judge_reason,
                "judge_issues": list(payload.judge_issues),
                "suggestions": list(payload.suggestions),
            }
            self.eval_results.append(persisted)
            return persisted

    repository = RecordingMonitorRunRepository()

    gateway = LocalToolGateway()
    gateway.register(
        "rss_fetch",
        lambda run_id, topic: ToolResponse.success(
            tool_name="rss_fetch",
            summary="No RSS candidates.",
            data={"run_id": run_id, "candidates": []},
        ),
    )
    gateway.register(
        "mock_search",
        lambda run_id, topic: ToolResponse.success(
            tool_name="search_news",
            summary="onesearch_mcp failed; used mock_search fallback.",
            data={"run_id": run_id, "candidates": []},
            metadata={
                "provider": "onesearch_mcp",
                "fallback_provider": "mock_search",
                "used_fallback": True,
                "fallback_reason": "onesearch unavailable",
            },
        ),
    )
    gateway.register(
        "fetch_article_content",
        lambda candidates: ToolResponse.success(
            tool_name="fetch_article_content",
            summary="No fetched contents.",
            data={"candidates": []},
        ),
    )
    gateway.register(
        "extract_article",
        lambda run_id, topic, candidates: ToolResponse.success(
            tool_name="extract_article",
            summary="No extracted items.",
            data={"articles": [], "skipped_candidate_ids": []},
        ),
    )
    gateway.register(
        "deduplicate_items",
        lambda articles: ToolResponse.success(
            tool_name="deduplicate_items",
            summary="No deduped items.",
            data={"articles": [], "deduped_count": 0, "dropped_candidate_ids": []},
        ),
    )
    gateway.register(
        "score_candidate",
        lambda topic, articles: ToolResponse.success(
            tool_name="score_candidate",
            summary="No scored items.",
            data={"articles": []},
        ),
    )
    gateway.register(
        "decide_push",
        lambda run_id, topic, articles, push_history: ToolResponse.success(
            tool_name="decide_push",
            summary="No push decisions.",
            data={"pushes": [], "push_count": 0},
        ),
    )

    graph = build_monitor_graph(
        llm=MockLLM(),
        gateway=gateway,
        run_repository=repository,
    )

    result = graph.invoke(
        {
            "run_id": "run_onesearch_event",
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
            "source_plan": ["search_news"],
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

    fallback_event = next(
        event for event in result["events"] if event["event_type"] == "fallback_used"
    )
    assert fallback_event["payload"]["provider"] == "onesearch_mcp"
    assert fallback_event["payload"]["fallback_provider"] == "mock_search"
    assert fallback_event["payload"]["fallback_reason"] == "onesearch unavailable"
    assert result["eval_result"]["provider_fallback_count"] == 1


def test_supervisor_finalize_indexes_candidate_history_when_opensearch_enabled() -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeIndexClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def put(self, url: str, **kwargs: object) -> FakeResponse:
            self.requests.append({"url": url, **kwargs})
            return FakeResponse()

    class RecordingRepository:
        def __init__(self) -> None:
            self.candidate_records: list[dict[str, object]] = []
            self.eval_results: list[dict[str, object]] = []
            self.monitor_runs: list[object] = []
            self.run_events: list[dict[str, object]] = []

        def upsert_extracted_item_records(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            return []

        def upsert_decision_records(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            return []

        def upsert_candidate_records(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            persisted = [
                {
                    "candidate_id": payload.candidate_id,
                    "run_id": payload.run_id,
                    "topic_id": payload.topic_id,
                    "source_type": payload.source_type,
                    "source_name": payload.source_name,
                    "title": payload.title,
                    "url": payload.url,
                    "raw_summary": payload.raw_summary,
                    "content": payload.content,
                    "score": payload.score,
                    "decision": payload.decision,
                    "decision_reason": payload.decision_reason,
                }
                for payload in payloads
            ]
            self.candidate_records.extend(persisted)
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
                "raw_summary_count": payload.raw_summary_count,
                "browser_fallback_count": payload.browser_fallback_count,
                "provider_fallback_count": payload.provider_fallback_count,
                "judge_mode": payload.judge_mode,
                "judge_score": payload.judge_score,
                "judge_reason": payload.judge_reason,
                "judge_issues": list(payload.judge_issues),
                "suggestions": list(payload.suggestions),
                "created_at": datetime(2026, 6, 9, tzinfo=UTC),
            }
            self.eval_results.append(persisted)
            return persisted

        def upsert_monitor_run(self, payload: object) -> object:
            self.monitor_runs.append(payload)
            return payload

    repository = RecordingRepository()
    index_client = FakeIndexClient()
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        history_index_provider="opensearch",
        opensearch_base_url="http://localhost:9200",
        opensearch_index_name="industry-news-candidates",
    )
    state = {
        "run_id": "run_index_history",
        "topic_id": "topic_ai_agent",
        "topic": {"topic_id": "topic_ai_agent"},
        "retrieval_output": {
            "candidate_pool": [
                {
                    "candidate_id": "cand_001",
                    "run_id": "run_index_history",
                    "topic_id": "topic_ai_agent",
                    "source_type": "search",
                    "source_name": "OpenWebSearch",
                    "title": "OpenAI ships agent workflow",
                    "url": "https://example.com/agent",
                    "published_at": None,
                    "raw_summary": "Agent workflow update.",
                }
            ]
        },
        "extraction_output": {
            "fetched_contents": [
                {
                    "candidate_id": "cand_001",
                    "fetch_status": "fetched",
                    "content": "Full article body.",
                }
            ],
            "evidence_items": [],
        },
        "evaluation_output": {
            "scored_items": [{"candidate_id": "cand_001", "score": 0.91}],
            "final_decisions": [
                {
                    "candidate_id": "cand_001",
                    "run_id": "run_index_history",
                    "topic_id": "topic_ai_agent",
                    "extracted_id": None,
                    "source_type": "search",
                    "source_name": "OpenWebSearch",
                    "title": "OpenAI ships agent workflow",
                    "url": "https://example.com/agent",
                    "published_at": None,
                    "summary": "Agent workflow update.",
                    "score": 0.91,
                    "should_push": True,
                    "decision_reason": "Above threshold",
                }
            ],
            "eval_result": {
                "retrieved_count": 1,
                "deduped_count": 0,
                "dedup_rate": 1.0,
                "push_count": 1,
                "duplicate_push_count": 0,
                "tool_success_rate": 1.0,
                "fetch_success_rate": 1.0,
                "trace_completeness": 1.0,
                "raw_summary_count": 0,
                "browser_fallback_count": 0,
                "provider_fallback_count": 0,
                "judge_mode": "mock_rule_judge",
                "judge_score": 1.0,
                "judge_reason": "Mock judge found no rule-based quality issues.",
                "judge_issues": [],
                "suggestions": [],
            },
        },
        "events": [],
        "errors": [],
        "tool_results": [],
        "status": "running",
    }

    result = supervisor_finalize_node(
        state,
        run_repository=repository,
        settings=settings,
        history_index_http_client=index_client,
    )

    assert result["status"] == "completed"
    assert result["history_index_result"] == {
        "indexed_count": 1,
        "provider": "opensearch",
    }
    assert len(repository.candidate_records) == 1
    assert index_client.requests[0]["url"] == (
        "http://localhost:9200/industry-news-candidates/_doc/run_index_history-cand_001"
    )
    index_event = next(
        event for event in result["events"] if event["node"] == "index_history"
    )
    assert index_event["event_type"] == "node_completed"
    assert index_event["payload"]["indexed_count"] == 1


def test_supervisor_finalize_records_history_index_failure_without_failing_run() -> None:
    class FailingIndexClient:
        def put(self, url: str, **kwargs: object) -> object:
            raise RuntimeError("opensearch unavailable")

    class RecordingRepository:
        def __init__(self) -> None:
            self.candidate_records: list[dict[str, object]] = []
            self.run_events: list[dict[str, object]] = []

        def upsert_extracted_item_records(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            return []

        def upsert_decision_records(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            return []

        def upsert_candidate_records(
            self,
            payloads: tuple[object, ...],
        ) -> list[dict[str, object]]:
            persisted = [
                {
                    "candidate_id": payload.candidate_id,
                    "run_id": payload.run_id,
                    "topic_id": payload.topic_id,
                    "source_type": payload.source_type,
                    "source_name": payload.source_name,
                    "title": payload.title,
                    "url": payload.url,
                    "raw_summary": payload.raw_summary,
                    "content": payload.content,
                    "score": payload.score,
                    "decision": payload.decision,
                    "decision_reason": payload.decision_reason,
                }
                for payload in payloads
            ]
            self.candidate_records.extend(persisted)
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
            return {
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
                "raw_summary_count": payload.raw_summary_count,
                "browser_fallback_count": payload.browser_fallback_count,
                "provider_fallback_count": payload.provider_fallback_count,
                "judge_mode": payload.judge_mode,
                "judge_score": payload.judge_score,
                "judge_reason": payload.judge_reason,
                "judge_issues": list(payload.judge_issues),
                "suggestions": list(payload.suggestions),
                "created_at": datetime(2026, 6, 9, tzinfo=UTC),
            }

        def upsert_monitor_run(self, payload: object) -> object:
            return payload

    repository = RecordingRepository()
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        history_index_provider="opensearch",
        opensearch_base_url="http://localhost:9200",
    )
    state = {
        "run_id": "run_index_failure",
        "topic_id": "topic_ai_agent",
        "topic": {"topic_id": "topic_ai_agent"},
        "retrieval_output": {
            "candidate_pool": [
                {
                    "candidate_id": "cand_001",
                    "run_id": "run_index_failure",
                    "topic_id": "topic_ai_agent",
                    "source_type": "search",
                    "source_name": "OpenWebSearch",
                    "title": "OpenAI ships agent workflow",
                    "url": "https://example.com/agent",
                    "published_at": None,
                    "raw_summary": "Agent workflow update.",
                }
            ]
        },
        "extraction_output": {
            "fetched_contents": [
                {
                    "candidate_id": "cand_001",
                    "fetch_status": "fetched",
                    "content": "Full article body.",
                }
            ],
            "evidence_items": [],
        },
        "evaluation_output": {
            "scored_items": [{"candidate_id": "cand_001", "score": 0.91}],
            "final_decisions": [
                {
                    "candidate_id": "cand_001",
                    "run_id": "run_index_failure",
                    "topic_id": "topic_ai_agent",
                    "extracted_id": None,
                    "source_type": "search",
                    "source_name": "OpenWebSearch",
                    "title": "OpenAI ships agent workflow",
                    "url": "https://example.com/agent",
                    "published_at": None,
                    "summary": "Agent workflow update.",
                    "score": 0.91,
                    "should_push": True,
                    "decision_reason": "Above threshold",
                }
            ],
            "eval_result": {
                "retrieved_count": 1,
                "deduped_count": 0,
                "dedup_rate": 1.0,
                "push_count": 1,
                "duplicate_push_count": 0,
                "tool_success_rate": 1.0,
                "fetch_success_rate": 1.0,
                "trace_completeness": 1.0,
                "raw_summary_count": 0,
                "browser_fallback_count": 0,
                "provider_fallback_count": 0,
                "judge_mode": "mock_rule_judge",
                "judge_score": 1.0,
                "judge_reason": "Mock judge found no rule-based quality issues.",
                "judge_issues": [],
                "suggestions": [],
            },
        },
        "events": [],
        "errors": [],
        "tool_results": [],
        "status": "running",
    }

    result = supervisor_finalize_node(
        state,
        run_repository=repository,
        settings=settings,
        history_index_http_client=FailingIndexClient(),
    )

    assert result["status"] == "completed"
    assert len(repository.candidate_records) == 1
    assert result["errors"][-1]["code"] == "history_index_failed"
    failed_event = next(
        event for event in result["events"] if event["node"] == "index_history"
    )
    assert failed_event["event_type"] == "node_failed"
    assert "opensearch unavailable" in failed_event["payload"]["error_message"]


def test_evaluate_run_node_only_closes_status_and_eval_result_without_persisting() -> None:
    class RecordingRepository:
        def __init__(self) -> None:
            self.candidate_records: list[dict[str, object]] = []

        def upsert_extracted_item_records(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
            self.candidate_records.append({"unexpected": "extracted"})
            return []

        def upsert_decision_records(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
            self.candidate_records.append({"unexpected": "decision"})
            return []

        def upsert_candidate_records(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
            self.candidate_records.append({"unexpected": "candidate"})
            return []

        def create_run_events(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
            self.candidate_records.append({"unexpected": "events"})
            return []

        def create_eval_result(self, payload: object) -> dict[str, object]:
            self.candidate_records.append({"unexpected": "eval"})
            return {"push_count": payload.push_count}

        def upsert_monitor_run(self, payload: object) -> object:
            self.candidate_records.append({"unexpected": "run"})
            return payload

    state = {
        "run_id": "run_eval_only",
        "topic_id": "topic_ai_agent",
        "candidate_items": [{"candidate_id": "cand_001"}],
        "fetched_contents": [{"candidate_id": "cand_001", "fetch_status": "fetched"}],
        "extracted_items": [{"candidate_id": "cand_001", "extraction_mode": "structured"}],
        "deduped_items": [{"candidate_id": "cand_001"}],
        "scored_items": [{"candidate_id": "cand_001", "score": 0.91}],
        "final_decisions": [{"candidate_id": "cand_001", "decision_reason": "Above threshold"}],
        "push_records": [{"push_id": "push_001"}],
        "evaluation_output": {},
        "events": [],
        "errors": [],
        "tool_results": [],
        "status": "running",
    }
    repository = RecordingRepository()

    result = evaluate_run_node(state, run_repository=repository, settings=None)

    assert result["status"] == "completed"
    assert result["evaluation_output"]["eval_result"]["push_count"] == 1
    assert repository.candidate_records == []


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
        self.candidate_records: list[dict[str, object]] = []
        self.extracted_records: list[dict[str, object]] = []
        self.decision_records: list[dict[str, object]] = []
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

    def upsert_candidate_records(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
        persisted = [
            {
                "candidate_id": payload.candidate_id,
                "run_id": payload.run_id,
                "topic_id": payload.topic_id,
                "source_type": payload.source_type,
                "source_name": payload.source_name,
                "title": payload.title,
                "url": payload.url,
                "published_at": payload.published_at,
                "raw_summary": payload.raw_summary,
                "fetch_status": payload.fetch_status,
                "content": payload.content,
                "structured_payload": payload.structured_payload,
                "score": payload.score,
                "decision": payload.decision,
                "decision_reason": payload.decision_reason,
                "created_at": self._created_at,
            }
            for payload in payloads
        ]
        existing_keys = {
            (record["run_id"], record["candidate_id"])
            for record in persisted
        }
        self.candidate_records = [
            record
            for record in self.candidate_records
            if (record["run_id"], record["candidate_id"]) not in existing_keys
        ]
        self.candidate_records.extend(persisted)
        return persisted

    def list_candidate_records(self, run_id: str) -> list[dict[str, object]]:
        return [
            record
            for record in self.candidate_records
            if record["run_id"] == run_id
        ]

    def upsert_extracted_item_records(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
        persisted = [
            {
                "extracted_id": payload.extracted_id,
                "run_id": payload.run_id,
                "topic_id": payload.topic_id,
                "candidate_id": payload.candidate_id,
                "source_type": payload.source_type,
                "source_name": payload.source_name,
                "title": payload.title,
                "url": payload.url,
                "published_at": payload.published_at,
                "summary": payload.summary,
                "keywords": list(payload.keywords),
                "content": payload.content,
                "content_fingerprint": payload.content_fingerprint,
                "fetch_status": payload.fetch_status,
                "fetch_error": payload.fetch_error,
                "extraction_mode": payload.extraction_mode,
                "structured_payload": payload.structured_payload,
                "created_at": self._created_at,
            }
            for payload in payloads
        ]
        existing_keys = {
            (record["run_id"], record["extracted_id"])
            for record in persisted
        }
        self.extracted_records = [
            record
            for record in self.extracted_records
            if (record["run_id"], record["extracted_id"]) not in existing_keys
        ]
        self.extracted_records.extend(persisted)
        return persisted

    def list_extracted_item_records(self, run_id: str) -> list[dict[str, object]]:
        return [
            record
            for record in self.extracted_records
            if record["run_id"] == run_id
        ]

    def upsert_decision_records(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
        persisted = [
            {
                "decision_id": payload.decision_id,
                "run_id": payload.run_id,
                "topic_id": payload.topic_id,
                "candidate_id": payload.candidate_id,
                "extracted_id": payload.extracted_id,
                "source_type": payload.source_type,
                "source_name": payload.source_name,
                "title": payload.title,
                "url": payload.url,
                "published_at": payload.published_at,
                "summary": payload.summary,
                "score": payload.score,
                "should_push": payload.should_push,
                "decision_reason": payload.decision_reason,
                "decision_payload": payload.decision_payload,
                "created_at": self._created_at,
            }
            for payload in payloads
        ]
        existing_keys = {
            (record["run_id"], record["decision_id"])
            for record in persisted
        }
        self.decision_records = [
            record
            for record in self.decision_records
            if (record["run_id"], record["decision_id"]) not in existing_keys
        ]
        self.decision_records.extend(persisted)
        return persisted

    def list_decision_records(self, run_id: str) -> list[dict[str, object]]:
        return [
            record
            for record in self.decision_records
            if record["run_id"] == run_id
        ]

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
        return sorted(
            self.eval_results.values(),
            key=lambda result: (result["created_at"], result["eval_id"]),
            reverse=True,
        )[0]

    def get_eval_summary(self) -> dict[str, object] | None:
        if not self.eval_results:
            return None
        results = list(self.eval_results.values())
        run_count = len(results)

        def _avg(key: str) -> float:
            return round(
                sum(float(result[key]) for result in results) / run_count,
                2,
            )

        latest = sorted(
            results,
            key=lambda result: (result["created_at"], result["eval_id"]),
            reverse=True,
        )[0]
        return {
            "run_count": run_count,
            "total_push_count": sum(int(result["push_count"]) for result in results),
            "total_duplicate_push_count": sum(
                int(result["duplicate_push_count"]) for result in results
            ),
            "total_raw_summary_count": sum(
                int(result["raw_summary_count"]) for result in results
            ),
            "total_browser_fallback_count": sum(
                int(result["browser_fallback_count"]) for result in results
            ),
            "total_provider_fallback_count": sum(
                int(result["provider_fallback_count"]) for result in results
            ),
            "avg_tool_success_rate": _avg("tool_success_rate"),
            "avg_fetch_success_rate": _avg("fetch_success_rate"),
            "avg_trace_completeness": _avg("trace_completeness"),
            "latest_eval": latest,
        }

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
            "raw_summary_count": payload.raw_summary_count,
            "browser_fallback_count": payload.browser_fallback_count,
            "provider_fallback_count": payload.provider_fallback_count,
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
    assert len(run_repository.candidate_records) == 3
    assert len(run_repository.extracted_records) == 3
    assert len(run_repository.decision_records) == 2
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


def test_candidates_endpoint_prefers_persisted_candidate_records() -> None:
    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()
    run_repository.monitor_runs["run_persisted_candidates"] = MonitorRunRecord(
        run_id="run_persisted_candidates",
        topic_id="topic_ai_agent",
        status="completed",
        state_snapshot={
            "run_id": "run_persisted_candidates",
            "topic_id": "topic_ai_agent",
            "candidate_items": [],
        },
        error_summary=None,
        started_at=datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
        finished_at=datetime(2026, 6, 9, 12, 5, tzinfo=UTC),
        created_at=datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
    )
    run_repository.candidate_records.append(
        {
            "candidate_id": "cand_persisted_001",
            "run_id": "run_persisted_candidates",
            "topic_id": "topic_ai_agent",
            "source_type": "search",
            "source_name": "Persisted Search",
            "title": "Persisted candidate",
            "url": "https://example.com/persisted-candidate",
            "published_at": None,
            "raw_summary": "Persisted summary",
            "fetch_status": "pending",
            "content": "",
            "structured_payload": {},
            "score": None,
            "decision": None,
            "decision_reason": None,
            "created_at": datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
        }
    )

    with _build_monitor_client(topic_repository, run_repository) as client:
        response = client.get("/api/monitor/runs/run_persisted_candidates/candidates")

    assert response.status_code == 200
    payload = response.json()
    assert [candidate["candidate_id"] for candidate in payload["candidates"]] == [
        "cand_persisted_001"
    ]


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


def test_eval_run_route_uses_created_at_for_latest_eval() -> None:
    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()
    run_repository.eval_results["run_999"] = {
        "eval_id": "eval_001",
        "run_id": "run_999",
        "topic_id": "topic_ai_agent",
        "retrieved_count": 1,
        "deduped_count": 1,
        "dedup_rate": 0.0,
        "push_count": 0,
        "duplicate_push_count": 0,
        "tool_success_rate": 1.0,
        "fetch_success_rate": 1.0,
        "trace_completeness": 1.0,
        "raw_summary_count": 0,
        "browser_fallback_count": 0,
        "provider_fallback_count": 0,
        "suggestions": [],
        "created_at": datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
    }
    run_repository.eval_results["run_001"] = {
        "eval_id": "eval_002",
        "run_id": "run_001",
        "topic_id": "topic_ai_agent",
        "retrieved_count": 2,
        "deduped_count": 2,
        "dedup_rate": 0.0,
        "push_count": 1,
        "duplicate_push_count": 0,
        "tool_success_rate": 1.0,
        "fetch_success_rate": 1.0,
        "trace_completeness": 1.0,
        "raw_summary_count": 0,
        "browser_fallback_count": 0,
        "provider_fallback_count": 0,
        "suggestions": [],
        "created_at": datetime(2026, 6, 9, 13, 0, tzinfo=UTC),
    }

    with _build_monitor_client(topic_repository, run_repository) as client:
        response = client.post("/api/eval/run")

    assert response.status_code == 200
    assert response.json()["run_id"] == "run_001"


def test_eval_summary_returns_quality_trend_metrics() -> None:
    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()
    run_repository.eval_results["run_001"] = {
        "eval_id": "eval_001",
        "run_id": "run_001",
        "topic_id": "topic_ai_agent",
        "retrieved_count": 6,
        "deduped_count": 4,
        "dedup_rate": 0.33,
        "push_count": 1,
        "duplicate_push_count": 0,
        "tool_success_rate": 1.0,
        "fetch_success_rate": 0.5,
        "trace_completeness": 0.9,
        "raw_summary_count": 2,
        "browser_fallback_count": 1,
        "provider_fallback_count": 1,
        "suggestions": [],
        "created_at": datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
    }
    run_repository.eval_results["run_002"] = {
        "eval_id": "eval_002",
        "run_id": "run_002",
        "topic_id": "topic_ai_agent",
        "retrieved_count": 8,
        "deduped_count": 7,
        "dedup_rate": 0.12,
        "push_count": 3,
        "duplicate_push_count": 1,
        "tool_success_rate": 0.5,
        "fetch_success_rate": 1.0,
        "trace_completeness": 1.0,
        "raw_summary_count": 0,
        "browser_fallback_count": 2,
        "provider_fallback_count": 0,
        "suggestions": ["review provider fallback"],
        "created_at": datetime(2026, 6, 9, 13, 0, tzinfo=UTC),
    }

    with _build_monitor_client(topic_repository, run_repository) as client:
        response = client.get("/api/eval/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_count"] == 2
    assert payload["total_push_count"] == 4
    assert payload["total_duplicate_push_count"] == 1
    assert payload["total_raw_summary_count"] == 2
    assert payload["total_browser_fallback_count"] == 3
    assert payload["total_provider_fallback_count"] == 1
    assert payload["avg_tool_success_rate"] == 0.75
    assert payload["avg_fetch_success_rate"] == 0.75
    assert payload["avg_trace_completeness"] == 0.95
    assert payload["latest_eval"]["eval_id"] == "eval_002"


def test_persist_push_records_sends_webhook_notification_after_persisting() -> None:
    run_repository = InMemoryMonitorRunRepository()
    gateway = LocalToolGateway()
    notification_calls: list[dict[str, object]] = []

    def notification_tool(
        run_id: str,
        topic_id: str,
        push_records: list[dict[str, object]],
    ) -> ToolResponse:
        notification_calls.append(
            {
                "run_id": run_id,
                "topic_id": topic_id,
                "push_records": push_records,
            }
        )
        return ToolResponse.success(
            tool_name="notification_send",
            summary="Sent webhook notification.",
            data={"status": "sent", "sent_count": len(push_records)},
            metadata={"notification_provider": "webhook"},
        )

    gateway.register("notification_send", notification_tool)
    state = {
        "run_id": "run_notify_success",
        "topic_id": "topic_ai_agent",
        "final_decisions": [
            {
                "run_id": "run_notify_success",
                "topic_id": "topic_ai_agent",
                "candidate_id": "cand_001",
                "extracted_id": "ext_001",
                "title": "OpenAI ships enterprise agent workflow",
                "url": "https://example.com/agent-workflow",
                "summary": "Enterprise workflow.",
                "should_push": True,
                "score": 0.91,
                "decision_reason": "score meets threshold",
            }
        ],
        "push_history": [],
        "events": [],
        "errors": [],
    }

    result = persist_push_records_node(
        state,
        run_repository=run_repository,
        gateway=gateway,
    )

    assert len(run_repository.push_records) == 1
    assert len(notification_calls) == 1
    assert notification_calls[0]["run_id"] == "run_notify_success"
    assert len(notification_calls[0]["push_records"]) == 1
    assert result["notification_result"]["status"] == "sent"
    notification_event = next(
        event for event in result["events"] if event["node"] == "notification_send"
    )
    assert notification_event["event_type"] == "notification_sent"
    assert notification_event["payload"]["provider"] == "webhook"
    assert result["errors"] == []


def test_persist_push_records_records_notification_failure_without_rollback() -> None:
    run_repository = InMemoryMonitorRunRepository()
    gateway = LocalToolGateway()

    def failing_notification_tool(
        run_id: str,
        topic_id: str,
        push_records: list[dict[str, object]],
    ) -> ToolResponse:
        return ToolResponse.failure(
            tool_name="notification_send",
            code="webhook_failed",
            message="webhook timeout",
            summary="Notification delivery failed.",
            metadata={"notification_provider": "webhook"},
        )

    gateway.register("notification_send", failing_notification_tool)
    state = {
        "run_id": "run_notify_failure",
        "topic_id": "topic_ai_agent",
        "final_decisions": [
            {
                "run_id": "run_notify_failure",
                "topic_id": "topic_ai_agent",
                "candidate_id": "cand_001",
                "extracted_id": "ext_001",
                "title": "OpenAI ships enterprise agent workflow",
                "url": "https://example.com/agent-workflow",
                "summary": "Enterprise workflow.",
                "should_push": True,
                "score": 0.91,
                "decision_reason": "score meets threshold",
            }
        ],
        "push_history": [],
        "events": [],
        "errors": [],
    }

    result = persist_push_records_node(
        state,
        run_repository=run_repository,
        gateway=gateway,
    )

    assert len(run_repository.push_records) == 1
    assert result["push_records"]
    assert result["errors"] == [
        {
            "tool_name": "notification_send",
            "code": "webhook_failed",
            "message": "webhook timeout",
            "details": {},
        }
    ]
    failure_event = next(
        event for event in result["events"] if event["node"] == "notification_send"
    )
    assert failure_event["event_type"] == "node_failed"
    assert failure_event["payload"]["provider"] == "webhook"


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


def test_worker_acknowledges_queue_message_when_skipping_duplicate_active_run() -> None:
    class RecordingQueue:
        def __init__(self, message: RunQueueMessage) -> None:
            self.message = message
            self.acknowledged: list[tuple[str, str | None]] = []

        def enqueue(self, message: RunQueueMessage) -> dict[str, object]:
            return {
                "status": "queued",
                "topic_id": message.topic_id,
                "trigger": message.trigger,
            }

        def dequeue(self) -> RunQueueMessage | None:
            current = self.message
            self.message = None  # type: ignore[assignment]
            return current

        def acknowledge(self, delivery: RunQueueMessage) -> None:
            self.acknowledged.append((delivery.topic_id, delivery.queue_message_id))

        def requeue(self, delivery: RunQueueMessage, *, reason: str) -> None:
            raise AssertionError("active-run skip path must not requeue")

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
        run_id="run_active_ack_skip",
        topic_id=topic.topic_id,
        status="running",
        state_snapshot={
            "run_id": "run_active_ack_skip",
            "topic_id": topic.topic_id,
            "trigger": "scheduler",
            "status": "running",
        },
        error_summary=None,
        started_at=datetime(2026, 6, 24, 9, 0, tzinfo=UTC),
        finished_at=None,
        created_at=datetime(2026, 6, 24, 9, 0, tzinfo=UTC),
    )
    run_repository.monitor_runs[active_run.run_id] = active_run
    queue = RecordingQueue(
        RunQueueMessage(
            topic_id=topic.topic_id,
            trigger="scheduler",
            enqueued_at=datetime(2026, 6, 24, 9, 5, tzinfo=UTC),
            queue_message_id="1710000000000-0",
            queue_stream="industry_news_agent:run_stream",
        )
    )

    worker = MonitorWorkerService(
        topic_repository=topic_repository,
        run_repository=run_repository,
        llm=MockLLM(),
        queue=queue,
    )

    result = worker.process_next()

    assert result is not None
    assert result["status"] == "skipped_active_run"
    assert result["run_id"] == active_run.run_id
    assert queue.acknowledged == [(topic.topic_id, "1710000000000-0")]


def test_worker_persists_active_run_guard_event_with_memory_coordination_backend() -> None:
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
        run_id="run_active_guard",
        topic_id=topic.topic_id,
        status="running",
        state_snapshot={
            "run_id": "run_active_guard",
            "topic_id": topic.topic_id,
            "trigger": "scheduler",
            "status": "running",
        },
        error_summary=None,
        started_at=datetime(2026, 6, 24, 9, 0, tzinfo=UTC),
        finished_at=None,
        created_at=datetime(2026, 6, 24, 9, 0, tzinfo=UTC),
    )
    run_repository.monitor_runs[active_run.run_id] = active_run
    queue = InMemoryRunQueue()
    queue.enqueue(RunQueueMessage(topic_id=topic.topic_id, trigger="scheduler"))

    worker = MonitorWorkerService(
        topic_repository=topic_repository,
        run_repository=run_repository,
        llm=MockLLM(),
        queue=queue,
    )

    result = worker.process_next()

    assert result is not None
    assert result["status"] == "skipped_active_run"
    events = run_repository.list_run_events(active_run.run_id)
    assert events[0]["event_type"] == "governance_skipped"
    assert events[0]["payload"]["active_run_id"] == "run_active_guard"
    assert events[0]["payload"]["coordination_backend"] == "memory"


def test_worker_persists_active_run_guard_event_with_redis_stream_coordination_backend() -> None:
    class FakeRedisStreamClient:
        def xgroup_create(
            self,
            name: str,
            groupname: str,
            id: str,
            mkstream: bool,
        ) -> None:
            return None

        def xreadgroup(
            self,
            *,
            groupname: str,
            consumername: str,
            streams: dict[str, str],
            count: int,
            block: int,
        ) -> list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]:
            return [
                (
                    b"industry_news_agent:run_stream",
                    [
                        (
                            b"1710000000000-0",
                            {
                                b"topic_id": b"topic_ai_agent",
                                b"trigger": b"scheduler",
                                b"enqueued_at": b"2026-06-24T09:00:00Z",
                            },
                        )
                    ],
                )
            ]

        def xack(self, name: str, groupname: str, id: bytes) -> int:
            return 1

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
        run_id="run_active_guard_redis",
        topic_id=topic.topic_id,
        status="running",
        state_snapshot={
            "run_id": "run_active_guard_redis",
            "topic_id": topic.topic_id,
            "trigger": "scheduler",
            "status": "running",
        },
        error_summary=None,
        started_at=datetime(2026, 6, 24, 9, 0, tzinfo=UTC),
        finished_at=None,
        created_at=datetime(2026, 6, 24, 9, 0, tzinfo=UTC),
    )
    run_repository.monitor_runs[active_run.run_id] = active_run
    queue = RedisStreamRunQueue(FakeRedisStreamClient())

    worker = MonitorWorkerService(
        topic_repository=topic_repository,
        run_repository=run_repository,
        llm=MockLLM(),
        queue=queue,
    )

    result = worker.process_next()

    assert result is not None
    assert result["status"] == "skipped_active_run"
    events = run_repository.list_run_events(active_run.run_id)
    assert events[0]["event_type"] == "governance_skipped"
    assert events[0]["payload"]["active_run_id"] == "run_active_guard_redis"
    assert events[0]["payload"]["coordination_backend"] == "redis_stream"


def test_scheduler_job_enqueues_message_with_scheduler_trigger() -> None:
    queue = InMemoryRunQueue()
    result = enqueue_topic_run("topic_001", queue=queue, trigger="scheduler")
    message = queue.dequeue()

    assert result["status"] == "queued"
    assert message is not None
    assert message.topic_id == "topic_001"
    assert message.trigger == "scheduler"


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
        max_retries=0,
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


def test_worker_requeues_retryable_failure_and_stops_current_delivery(monkeypatch) -> None:
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
    class RecordingQueue(InMemoryRunQueue):
        def __init__(self) -> None:
            super().__init__()
            self.acknowledged: list[tuple[str, str | None]] = []
            self.requeued: list[dict[str, str | None]] = []

        def acknowledge(self, delivery: RunQueueMessage) -> None:
            self.acknowledged.append((delivery.topic_id, delivery.queue_message_id))

        def requeue(self, delivery: RunQueueMessage, *, reason: str) -> None:
            self.requeued.append(
                {
                    "topic_id": delivery.topic_id,
                    "queue_message_id": delivery.queue_message_id,
                    "reason": reason,
                }
            )
            super().requeue(delivery, reason=reason)

    queue = RecordingQueue()
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
    assert result["status"] == "queued_for_retry"
    assert result["retry_count"] == 0
    assert attempts["count"] == 1
    run_record = run_repository.get_monitor_run(result["run_id"])
    assert run_record is not None
    assert run_record.status == "running"
    events = run_repository.list_run_events(result["run_id"])
    dequeue_event = next(event for event in events if event["node"] == "worker_dequeue")
    retry_event = next(event for event in events if event["node"] == "worker_retry")
    assert dequeue_event["payload"]["queue_wait_ms"] >= 0
    assert retry_event["event_type"] == "governance_retry"
    assert retry_event["payload"]["attempt"] == 1
    assert retry_event["payload"]["max_retries"] == 1
    assert retry_event["payload"]["error_message"] == "transient failure"
    assert queue.requeued == [
        {
            "topic_id": topic.topic_id,
            "queue_message_id": None,
            "reason": "worker_retry",
        }
    ]
    assert queue.acknowledged == [(topic.topic_id, None)]
    queued_retry = queue.dequeue()
    assert queued_retry is not None
    assert queued_retry.topic_id == topic.topic_id
    assert queued_retry.trigger == "scheduler"
    assert queued_retry.retry_reason == "worker_retry"
    assert queued_retry.retry_count == 1
    assert queued_retry.max_retries == 1


def test_worker_marks_run_failed_after_retry_budget_is_exhausted_across_deliveries(
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

    class AlwaysFailingGraph:
        def invoke(self, state: dict[str, object]) -> dict[str, object]:
            raise RuntimeError("transient failure")

    monkeypatch.setattr(
        "app.scheduler.worker.build_monitor_graph",
        lambda llm, run_repository: AlwaysFailingGraph(),
    )

    worker = MonitorWorkerService(
        topic_repository=topic_repository,
        run_repository=run_repository,
        llm=MockLLM(),
        queue=queue,
        max_retries=1,
    )

    first_result = worker.process_next()

    assert first_result is not None
    assert first_result["status"] == "queued_for_retry"
    queued_retry = queue.dequeue()
    assert queued_retry is not None
    assert queued_retry.retry_count == 1
    assert queued_retry.max_retries == 1
    queue.enqueue(queued_retry)

    second_result = worker.process_next()

    assert second_result is not None
    assert second_result["status"] == "failed"
    assert second_result["retry_count"] == 1
    assert queue.dequeue() is None
    assert second_result["run_id"] == first_result["run_id"]
    first_run = run_repository.get_monitor_run(first_result["run_id"])
    assert first_run is not None
    assert first_run.status == "failed"
    assert first_run.state_snapshot["retry_count"] == 2
    failure_event = next(
        event
        for event in run_repository.list_run_events(second_result["run_id"])
        if event["node"] == "worker_failed"
    )
    assert failure_event["payload"]["attempt"] == 2
    assert failure_event["payload"]["max_retries"] == 1
    assert failure_event["payload"]["error_message"] == "transient failure"


def test_worker_retry_delivery_uses_queued_run_id_instead_of_current_active_run(
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
    original_run = MonitorRunRecord(
        run_id="run_retry_original",
        topic_id=topic.topic_id,
        status="running",
        state_snapshot={
            "run_id": "run_retry_original",
            "topic_id": topic.topic_id,
            "trigger": "scheduler",
            "status": "running",
        },
        error_summary=None,
        started_at=datetime(2026, 6, 24, 9, 0, tzinfo=UTC),
        finished_at=None,
        created_at=datetime(2026, 6, 24, 9, 0, tzinfo=UTC),
    )
    newer_active_run = MonitorRunRecord(
        run_id="run_unrelated_active",
        topic_id=topic.topic_id,
        status="running",
        state_snapshot={
            "run_id": "run_unrelated_active",
            "topic_id": topic.topic_id,
            "trigger": "manual",
            "status": "running",
        },
        error_summary=None,
        started_at=datetime(2026, 6, 24, 9, 5, tzinfo=UTC),
        finished_at=None,
        created_at=datetime(2026, 6, 24, 9, 5, tzinfo=UTC),
    )
    run_repository.monitor_runs[original_run.run_id] = original_run
    run_repository.monitor_runs[newer_active_run.run_id] = newer_active_run
    queue = InMemoryRunQueue()
    queue.enqueue(
        RunQueueMessage(
            topic_id=topic.topic_id,
            trigger="scheduler",
            run_id=original_run.run_id,
            retry_reason="worker_retry",
            retry_count=1,
            max_retries=2,
        )
    )
    observed_run_ids: list[str] = []

    class SuccessfulGraph:
        def invoke(self, state: dict[str, object]) -> dict[str, object]:
            observed_run_ids.append(str(state["run_id"]))
            return {**state, "status": "completed"}

    monkeypatch.setattr(
        "app.scheduler.worker.build_monitor_graph",
        lambda llm, run_repository: SuccessfulGraph(),
    )

    worker = MonitorWorkerService(
        topic_repository=topic_repository,
        run_repository=run_repository,
        llm=MockLLM(),
        queue=queue,
        max_retries=2,
    )

    result = worker.process_next()

    assert result is not None
    assert result["status"] == "completed"
    assert result["run_id"] == "run_retry_original"
    assert observed_run_ids == ["run_retry_original"]
    unrelated_run = run_repository.get_monitor_run("run_unrelated_active")
    assert unrelated_run is not None
    assert unrelated_run.status == "running"


def test_worker_acknowledges_queue_message_after_successful_completion(
    monkeypatch,
) -> None:
    class RecordingQueue:
        def __init__(self, message: RunQueueMessage) -> None:
            self.message = message
            self.acknowledged: list[tuple[str, str | None]] = []

        def enqueue(self, message: RunQueueMessage) -> dict[str, object]:
            return {"status": "queued", "topic_id": message.topic_id, "trigger": message.trigger}

        def dequeue(self) -> RunQueueMessage | None:
            current = self.message
            self.message = None  # type: ignore[assignment]
            return current

        def acknowledge(self, delivery: RunQueueMessage) -> None:
            self.acknowledged.append((delivery.topic_id, delivery.queue_message_id))

        def requeue(self, delivery: RunQueueMessage, *, reason: str) -> None:
            raise AssertionError("success path must not requeue")

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
    queue = RecordingQueue(
        RunQueueMessage(
            topic_id=topic.topic_id,
            trigger="scheduler",
            queue_message_id="1710000000000-0",
            queue_stream="industry_news_agent:run_stream",
        )
    )

    class SuccessfulGraph:
        def invoke(self, state: dict[str, object]) -> dict[str, object]:
            return {**state, "status": "completed"}

    monkeypatch.setattr(
        "app.scheduler.worker.build_monitor_graph",
        lambda llm, run_repository: SuccessfulGraph(),
    )

    worker = MonitorWorkerService(
        topic_repository=topic_repository,
        run_repository=run_repository,
        llm=MockLLM(),
        queue=queue,
    )

    result = worker.process_next()

    assert result is not None
    assert result["status"] == "completed"
    assert queue.acknowledged == [(topic.topic_id, "1710000000000-0")]


def test_redis_stream_queued_run_can_be_consumed_end_to_end_by_worker() -> None:
    class FakeRedisStreamClient:
        def __init__(self) -> None:
            self.created_groups: list[dict[str, object]] = []
            self.added: list[dict[str, object]] = []
            self.acked: list[dict[str, object]] = []
            self.pending_messages: list[
                tuple[bytes, dict[bytes, bytes]]
            ] = []

        def xgroup_create(
            self,
            name: str,
            groupname: str,
            id: str,
            mkstream: bool,
        ) -> None:
            self.created_groups.append(
                {
                    "name": name,
                    "groupname": groupname,
                    "id": id,
                    "mkstream": mkstream,
                }
            )

        def xadd(self, name: str, fields: dict[str, str]) -> str:
            self.added.append({"name": name, "fields": fields})
            return "1710000000000-0"

        def xreadgroup(
            self,
            *,
            groupname: str,
            consumername: str,
            streams: dict[str, str],
            count: int,
            block: int,
        ) -> list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]:
            if not self.pending_messages:
                return []
            return [(b"industry_news_agent:run_stream", [self.pending_messages.pop(0)])]

        def xack(self, name: str, groupname: str, id: bytes) -> int:
            self.acked.append({"name": name, "groupname": groupname, "id": id})
            return 1

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
    client = FakeRedisStreamClient()
    client.pending_messages.append(
        (
            b"1710000000000-0",
            {
                b"topic_id": topic.topic_id.encode("utf-8"),
                b"trigger": b"scheduler",
                b"enqueued_at": b"2026-06-24T09:00:00Z",
            },
        )
    )
    queue = RedisStreamRunQueue(client)

    worker = MonitorWorkerService(
        topic_repository=topic_repository,
        run_repository=run_repository,
        llm=MockLLM(),
        queue=queue,
    )

    result = worker.process_next()

    assert result is not None
    assert result["topic_id"] == topic.topic_id
    assert result["status"] == "completed"
    run_record = run_repository.get_monitor_run(result["run_id"])
    assert run_record is not None
    assert run_record.status == "completed"
    assert client.acked == [
        {
            "name": "industry_news_agent:run_stream",
            "groupname": "monitor-workers",
            "id": b"1710000000000-0",
        }
    ]


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


def test_worker_acknowledges_queue_message_only_after_failed_run_is_persisted(
    monkeypatch,
) -> None:
    class RecordingQueue:
        def __init__(self, message: RunQueueMessage) -> None:
            self.message = message
            self.acknowledged: list[tuple[str, str | None]] = []
            self.requeued: list[dict[str, str | None]] = []

        def enqueue(self, message: RunQueueMessage) -> dict[str, object]:
            return {"status": "queued", "topic_id": message.topic_id, "trigger": message.trigger}

        def dequeue(self) -> RunQueueMessage | None:
            current = self.message
            self.message = None  # type: ignore[assignment]
            return current

        def acknowledge(self, delivery: RunQueueMessage) -> None:
            self.acknowledged.append((delivery.topic_id, delivery.queue_message_id))

        def requeue(self, delivery: RunQueueMessage, *, reason: str) -> None:
            self.requeued.append(
                {
                    "topic_id": delivery.topic_id,
                    "queue_message_id": delivery.queue_message_id,
                    "reason": reason,
                }
            )

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
    delivery = RunQueueMessage(
        topic_id=topic.topic_id,
        trigger="scheduler",
        enqueued_at=datetime(2026, 6, 24, 9, 0, tzinfo=UTC),
        queue_message_id="1710000000000-0",
        queue_stream="industry_news_agent:run_stream",
    )
    queue = RecordingQueue(delivery)

    class FailingGraph:
        def invoke(self, state: dict[str, object]) -> dict[str, object]:
            raise RuntimeError("graph failed")

    monkeypatch.setattr(
        "app.scheduler.worker.build_monitor_graph",
        lambda llm, run_repository: FailingGraph(),
    )

    worker = MonitorWorkerService(
        topic_repository=topic_repository,
        run_repository=run_repository,
        llm=MockLLM(),
        queue=queue,
        max_retries=0,
    )

    result = worker.process_next()

    assert result is not None
    assert result["status"] == "failed"
    run_record = run_repository.get_monitor_run(result["run_id"])
    assert run_record is not None
    assert run_record.status == "failed"
    assert queue.requeued == []
    assert queue.acknowledged == [(topic.topic_id, "1710000000000-0")]


def test_worker_timeout_blocks_late_background_persistence(monkeypatch) -> None:
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
    release_graph = Event()
    graph_run_repository: object | None = None

    class LateWritingGraph:
        def __init__(self, repository: object) -> None:
            self.repository = repository

        def invoke(self, state: dict[str, object]) -> dict[str, object]:
            assert release_graph.wait(timeout=1.0)
            self.repository.create_run_events(
                (
                    type(
                        "Payload",
                        (),
                        {
                            "run_id": state["run_id"],
                            "topic_id": state["topic_id"],
                            "event_type": "late_write",
                            "node": "late_write",
                            "message": "late background write",
                            "payload": {"source": "background"},
                            "elapsed_ms": None,
                        },
                    )(),
                )
            )
            return {**state, "status": "completed"}

    monkeypatch.setattr(
        "app.scheduler.worker.build_monitor_graph",
        lambda llm, run_repository: LateWritingGraph(run_repository),
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
    release_graph.set()
    time.sleep(0.05)

    events = run_repository.list_run_events(result["run_id"])
    assert all(event["node"] != "late_write" for event in events)
