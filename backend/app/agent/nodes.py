from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agent.contracts import (
    build_empty_business_memory,
    build_empty_candidate_task_output,
    build_empty_evaluation_output,
    build_empty_extraction_output,
    build_empty_planner_output,
    build_empty_retrieval_output,
    build_empty_run_context,
)
from app.agent.candidate_orchestrator import CandidateTaskOrchestrator
from app.agent.extraction_agent import ExtractionAgent
from app.agent.evaluation_agent import EvaluationAgent
from app.agent.planner_agent import PlannerAgent
from app.agent.retrieval_agent import RetrievalAgent
from app.core.config import Settings
from app.eval.judge import build_eval_judge
from app.eval.rule_scorer import score_run
from app.integrations.runtime_summary import build_integration_runtime
from app.llm.base import BaseLLMClient
from app.llm.mock_client import MockLLM
from app.mcp.local_gateway import LocalToolGateway
from app.observability.event_logger import append_event
from app.rag.hybrid_retriever import retrieve_hybrid_context
from app.rag.knowledge_loader import load_knowledge_base
from app.search.history_index import build_history_index
from app.storage.repository import (
    CandidateRecordUpsertData,
    CandidateTaskRecordCreateData,
    DecisionRecordUpsertData,
    EvalResultCreateData,
    ExtractedItemRecordUpsertData,
    MonitorRunRepositoryProtocol,
    MonitorRunUpsertData,
    PushRecordCreateData,
    RunEventCreateData,
)
from app.tools.responses import ToolResponse


def _serialize_tool_response(response: ToolResponse) -> dict[str, Any]:
    return {
        "success": response.success,
        "tool_name": response.tool_name,
        "summary": response.summary,
        "metadata": dict(response.metadata),
        "error": (
            None
            if response.error is None
            else {
                "code": response.error.code,
                "message": response.error.message,
                "details": dict(response.error.details),
            }
        ),
    }


def _record_tool_result(state: dict[str, Any], response: ToolResponse) -> None:
    tool_results = list(state.get("tool_results", []))
    tool_results.append(_serialize_tool_response(response))
    state["tool_results"] = tool_results


def _record_tool_error(state: dict[str, Any], response: ToolResponse) -> None:
    errors = list(state.get("errors", []))
    if response.error is not None:
        errors.append(
            {
                "tool_name": response.tool_name,
                "code": response.error.code,
                "message": response.error.message,
                "details": dict(response.error.details),
            }
        )
    state["errors"] = errors


def _call_tool(
    state: dict[str, Any],
    gateway: LocalToolGateway,
    tool_name: str,
    **kwargs: Any,
) -> ToolResponse:
    response = gateway.call(tool_name, **kwargs)
    _record_tool_result(state, response)
    if not response.success:
        _record_tool_error(state, response)
        append_event(
            state,
            tool_name,
            response.summary,
            event_type="node_failed",
            payload={"tool_name": tool_name},
        )
        raise RuntimeError(f"{tool_name} failed: {response.summary}")
    return response


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _build_monitor_run_payload(state: dict[str, Any]) -> MonitorRunUpsertData:
    return MonitorRunUpsertData(
        run_id=str(state["run_id"]),
        topic_id=str(state["topic_id"]),
        status=str(state.get("status", "pending")),
        state_snapshot=_json_safe(dict(state)),
        error_summary=(
            None
            if not state.get("errors")
            else "; ".join(str(item.get("message", "")) for item in state["errors"])
        ),
        started_at=None,
        finished_at=None,
    )


def load_topic_node(
    state: dict[str, Any],
    run_repository: MonitorRunRepositoryProtocol | None = None,
) -> dict[str, Any]:
    return supervisor_bootstrap_node(state, run_repository)


def supervisor_bootstrap_node(
    state: dict[str, Any],
    run_repository: MonitorRunRepositoryProtocol | None = None,
) -> dict[str, Any]:
    state["status"] = "running"
    if run_repository is not None:
        state["push_history"] = run_repository.list_push_history(str(state["topic_id"]))
    state["run_context"] = {
        **build_empty_run_context(
            run_id=str(state["run_id"]),
            topic_id=str(state["topic_id"]),
        ),
        "topic": dict(state.get("topic", {})),
        "trigger": str(state.get("trigger", "manual")),
        "status": "running",
        "errors": list(state.get("errors", [])),
        "events": list(state.get("events", [])),
    }
    state["business_memory"] = {
        **build_empty_business_memory(),
        "seed_keywords": list(state.get("seed_keywords", [])),
        "business_context": dict(state.get("business_context", {})),
        "push_history": list(state.get("push_history", [])),
        "trusted_sources": list(state.get("topic", {}).get("trusted_sources", [])),
    }
    state.setdefault("planner_output", build_empty_planner_output())
    state.setdefault("retrieval_output", build_empty_retrieval_output())
    state.setdefault("extraction_output", build_empty_extraction_output())
    state.setdefault("evaluation_output", build_empty_evaluation_output())
    append_event(state, "load_topic", "Loaded topic configuration.")
    state["run_context"]["events"] = list(state.get("events", []))
    if run_repository is not None:
        run_repository.upsert_monitor_run(_build_monitor_run_payload(state))
    return state


def retrieve_business_context_node(state: dict[str, Any]) -> dict[str, Any]:
    query = " ".join(
        [
            str(state["topic"].get("name", "")),
            *[str(item) for item in state.get("seed_keywords", [])],
        ]
    ).strip()
    state["business_context"] = retrieve_hybrid_context(
        load_knowledge_base(),
        query,
        top_k=3,
    )
    if state.get("business_memory"):
        state["business_memory"]["business_context"] = dict(state["business_context"])
    return append_event(
        state,
        "retrieve_business_context",
        "Retrieved business context from local knowledge base.",
        payload={
            "document_count": len(state["business_context"]["documents"]),
            "retrieval_mode": state["business_context"]["retrieval_mode"],
            "retrievers": list(state["business_context"]["retrievers"]),
        },
    )


def expand_queries_node(state: dict[str, Any], llm: BaseLLMClient) -> dict[str, Any]:
    state["expanded_queries"] = llm.expand_keywords(
        topic_name=str(state["topic"]["name"]),
        seed_keywords=state.get("seed_keywords", []),
    )
    if state.get("planner_output"):
        state["planner_output"]["expanded_queries"] = list(state["expanded_queries"])
    return append_event(
        state,
        "expand_queries",
        "Expanded keyword queries for the monitor run.",
        payload={"query_count": len(state["expanded_queries"])},
    )


def plan_sources_node(state: dict[str, Any]) -> dict[str, Any]:
    if not state.get("business_memory"):
        state["business_memory"] = {
            "seed_keywords": list(state.get("seed_keywords", [])),
            "business_context": dict(state.get("business_context", {})),
            "push_history": list(state.get("push_history", [])),
            "trusted_sources": list(state.get("topic", {}).get("trusted_sources", [])),
        }
    if not state.get("planner_output"):
        state["planner_output"] = {}

    PlannerAgent(llm=MockLLM()).run(state)
    return append_event(
        state,
        "plan_sources",
        "Planned candidate retrieval sources.",
        payload={"sources": list(state["source_plan"])},
    )


def retrieve_candidates_node(
    state: dict[str, Any],
    gateway: LocalToolGateway,
) -> dict[str, Any]:
    if not state.get("run_context"):
        state["run_context"] = {
            "run_id": str(state.get("run_id", "")),
            "topic_id": str(state.get("topic_id", "")),
            "topic": dict(state.get("topic", {})),
            "status": str(state.get("status", "created")),
            "errors": list(state.get("errors", [])),
            "events": list(state.get("events", [])),
        }
    if not state.get("planner_output"):
        state["planner_output"] = {
            "source_plan": [
                {"tool_name": tool_name, "priority": index + 1}
                for index, tool_name in enumerate(state.get("source_plan", []))
            ],
            "retrieval_strategy": {"mode": "rss_first"},
        }

    RetrievalAgent(gateway=gateway).run(state)
    return append_event(
        state,
        "retrieve_candidates",
        "Retrieved candidate items from planned sources.",
        payload={"count": len(state.get("candidate_items", []))},
    )


def fetch_contents_node(
    state: dict[str, Any],
    gateway: LocalToolGateway,
) -> dict[str, Any]:
    if not state.get("run_context"):
        state["run_context"] = {
            "run_id": str(state.get("run_id", "")),
            "topic_id": str(state.get("topic_id", "")),
            "topic": dict(state.get("topic", {})),
            "status": str(state.get("status", "created")),
            "errors": list(state.get("errors", [])),
            "events": list(state.get("events", [])),
        }
    if not state.get("retrieval_output"):
        state["retrieval_output"] = {"candidate_pool": list(state.get("candidate_items", []))}

    agent = ExtractionAgent(gateway=gateway)
    agent.fetch_contents(state)
    return append_event(
        state,
        "fetch_contents",
        "Fetched candidate content or preserved summary fallback inputs.",
        payload={"count": len(state["fetched_contents"])},
    )


def extract_structured_items_node(
    state: dict[str, Any],
    gateway: LocalToolGateway,
) -> dict[str, Any]:
    if not state.get("extraction_output"):
        state["extraction_output"] = {
            "fetched_contents": list(state.get("fetched_contents", [])),
            "evidence_items": list(state.get("extracted_items", [])),
            "extraction_failures": [],
            "content_fallbacks": [],
        }

    agent = ExtractionAgent(gateway=gateway)
    agent.extract_evidence(state)

    return append_event(
        state,
        "extract_structured_items",
        "Extracted structured article summaries.",
        payload={"count": len(state.get("extracted_items", []))},
    )


def deduplicate_items_node(
    state: dict[str, Any],
    gateway: LocalToolGateway,
) -> dict[str, Any]:
    response = _call_tool(
        state,
        gateway,
        "deduplicate_items",
        articles=state.get("extracted_items", []),
    )
    payload = response.data or {}
    state["deduped_items"] = list(payload.get("articles", []))
    return append_event(
        state,
        "deduplicate_items",
        "Deduplicated extracted article items.",
        payload={
            "count": len(state["deduped_items"]),
            "dropped_candidate_ids": list(payload.get("dropped_candidate_ids", [])),
        },
    )


def score_items_node(
    state: dict[str, Any],
    gateway: LocalToolGateway,
) -> dict[str, Any]:
    response = _call_tool(
        state,
        gateway,
        "score_candidate",
        topic=dict(state["topic"]),
        articles=state.get("deduped_items", []),
    )
    payload = response.data or {}
    state["scored_items"] = list(payload.get("articles", []))
    return append_event(
        state,
        "score_items",
        "Scored candidate items against topic rules.",
        payload={"count": len(state["scored_items"])},
    )


def decide_push_node(
    state: dict[str, Any],
    gateway: LocalToolGateway,
) -> dict[str, Any]:
    response = _call_tool(
        state,
        gateway,
        "decide_push",
        run_id=str(state["run_id"]),
        topic=dict(state["topic"]),
        articles=state.get("scored_items", []),
        push_history=state.get("push_history", []),
    )
    payload = response.data or {}
    decisions = list(payload.get("pushes", []))
    state["final_decisions"] = decisions
    state["decision_reasons"] = [
        str(item.get("decision_reason", "")) for item in decisions
    ]
    return append_event(
        state,
        "decide_push",
        "Calculated push decisions for scored candidates.",
        payload={
            "count": len(decisions),
            "push_count": payload.get("push_count", 0),
        },
    )


def persist_push_records_node(
    state: dict[str, Any],
    run_repository: MonitorRunRepositoryProtocol | None = None,
    gateway: LocalToolGateway | None = None,
) -> dict[str, Any]:
    evaluation_output = dict(state.get("evaluation_output", {}))
    final_decisions = list(
        evaluation_output.get("final_decisions", state.get("final_decisions", []))
    )
    pushed_at = datetime.now(UTC)
    candidate_push_records = [
        {**dict(item), "pushed_at": pushed_at}
        for item in final_decisions
        if item.get("should_push")
    ]
    if run_repository is not None:
        state["push_records"] = run_repository.create_push_records(
            tuple(
                PushRecordCreateData(
                    run_id=str(item["run_id"]),
                    topic_id=str(item["topic_id"]),
                    candidate_id=str(item["candidate_id"]),
                    extracted_id=(
                        None
                        if item.get("extracted_id") is None
                        else str(item["extracted_id"])
                    ),
                    title=str(item.get("title", "")),
                    url=str(item.get("url", "")),
                    summary=(
                        None if item.get("summary") is None else str(item.get("summary"))
                    ),
                    should_push=bool(item["should_push"]),
                    score=float(item["score"]),
                    decision_reason=(
                        None
                        if item.get("decision_reason") is None
                        else str(item["decision_reason"])
                    ),
                    pushed_at=pushed_at,
                )
                for item in candidate_push_records
            )
        )
        state["push_history"] = [
            *list(state.get("push_history", [])),
            *state["push_records"],
        ]
    else:
        state["push_records"] = candidate_push_records
    if state.get("evaluation_output"):
        state["evaluation_output"]["push_records"] = list(state["push_records"])
    append_event(
        state,
        "persist_push_records",
        "Persisted push records and updated push history.",
        payload={"count": len(state["push_records"])},
    )
    if gateway is not None and state["push_records"]:
        response = gateway.call(
            "notification_send",
            run_id=str(state["run_id"]),
            topic_id=str(state["topic_id"]),
            push_records=list(state["push_records"]),
        )
        _record_tool_result(state, response)
        state["notification_result"] = dict(response.data or {})
        provider = response.metadata.get("notification_provider")
        if response.success:
            status = str((response.data or {}).get("status", "sent"))
            event_type = (
                "notification_skipped"
                if status == "skipped"
                else "notification_sent"
            )
            append_event(
                state,
                "notification_send",
                response.summary,
                event_type=event_type,
                payload={
                    "provider": provider,
                    "status": status,
                    "sent_count": (response.data or {}).get("sent_count", 0),
                },
            )
        else:
            _record_tool_error(state, response)
            append_event(
                state,
                "notification_send",
                response.summary,
                event_type="node_failed",
                payload={
                    "provider": provider,
                    "error_code": (
                        None if response.error is None else response.error.code
                    ),
                    "error_message": (
                        None if response.error is None else response.error.message
                    ),
                },
            )
    return state


def _index_by_candidate_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(item["candidate_id"]): dict(item)
        for item in items
        if item.get("candidate_id") is not None
    }


def _parse_optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _build_history_index_query(state: dict[str, Any]) -> str:
    topic_name = str(state.get("topic", {}).get("name", "")).strip()
    final_decisions = list(state.get("final_decisions", []))

    preferred_item = next(
        (item for item in final_decisions if item.get("should_push")),
        final_decisions[0] if final_decisions else {},
    )
    title = str(preferred_item.get("title", "")).strip()
    decision_reason = str(preferred_item.get("decision_reason", "")).strip()

    parts = [part for part in (topic_name, title, decision_reason) if part]
    return " ".join(parts)


def _build_history_index_search_evidence(search_result: dict[str, Any]) -> dict[str, Any]:
    items = [
        {
            "candidate_id": str(item.get("candidate_id", "")),
            "title": str(item.get("title", "")),
        }
        for item in search_result.get("items", [])
    ]
    return {
        "provider": search_result.get("provider"),
        "query": search_result.get("query"),
        "status": "completed",
        "item_count": len(items),
        "items": items,
    }


def _build_history_index_exclusions(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "exclude_run_id": str(state.get("run_id", "")).strip() or None,
        "exclude_candidate_ids": None,
    }


def _build_history_index_search_failure_evidence(
    *,
    provider: Any,
    query: str,
    error_message: str,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "query": query,
        "status": "failed",
        "item_count": 0,
        "items": [],
        "error": {"message": error_message},
    }


def _build_candidate_payloads(state: dict[str, Any]) -> tuple[CandidateRecordUpsertData, ...]:
    fetched_by_id = _index_by_candidate_id(list(state.get("fetched_contents", [])))
    extracted_by_id = _index_by_candidate_id(list(state.get("extracted_items", [])))
    scored_by_id = _index_by_candidate_id(list(state.get("scored_items", [])))
    decisions_by_id = _index_by_candidate_id(list(state.get("final_decisions", [])))
    payloads: list[CandidateRecordUpsertData] = []

    for candidate in state.get("candidate_items", []):
        candidate_id = str(candidate["candidate_id"])
        fetched = fetched_by_id.get(candidate_id, {})
        extracted = extracted_by_id.get(candidate_id, {})
        scored = scored_by_id.get(candidate_id, {})
        decision = decisions_by_id.get(candidate_id, {})
        structured_payload = {
            "extracted": extracted,
            "score_breakdown": scored.get("score_breakdown"),
            "decision": decision,
        }

        payloads.append(
            CandidateRecordUpsertData(
                candidate_id=candidate_id,
                run_id=str(candidate["run_id"]),
                topic_id=str(candidate["topic_id"]),
                source_type=str(candidate["source_type"]),
                source_name=str(candidate["source_name"]),
                title=str(candidate["title"]),
                url=str(candidate["url"]),
                published_at=_parse_optional_datetime(candidate.get("published_at")),
                raw_summary=(
                    None
                    if candidate.get("raw_summary") is None
                    else str(candidate.get("raw_summary"))
                ),
                fetch_status=str(
                    fetched.get("fetch_status", candidate.get("fetch_status", "pending"))
                ),
                content=(
                    None
                    if fetched.get("content") is None
                    else str(fetched.get("content"))
                ),
                structured_payload=structured_payload,
                score=None if scored.get("score") is None else float(scored.get("score")),
                decision=(
                    None
                    if decision.get("should_push") is None
                    else ("push" if decision.get("should_push") else "skip")
                ),
                decision_reason=(
                    None
                    if decision.get("decision_reason") is None
                    else str(decision.get("decision_reason"))
                ),
            )
        )

    return tuple(payloads)


def _build_extracted_item_payloads(
    state: dict[str, Any],
) -> tuple[ExtractedItemRecordUpsertData, ...]:
    payloads: list[ExtractedItemRecordUpsertData] = []

    for item in state.get("extracted_items", []):
        payloads.append(
            ExtractedItemRecordUpsertData(
                extracted_id=str(item["extracted_id"]),
                run_id=str(item["run_id"]),
                topic_id=str(item["topic_id"]),
                candidate_id=str(item["candidate_id"]),
                source_type=str(item["source_type"]),
                source_name=str(item["source_name"]),
                title=str(item["title"]),
                url=str(item["url"]),
                published_at=_parse_optional_datetime(item.get("published_at")),
                summary=(
                    None if item.get("summary") is None else str(item.get("summary"))
                ),
                keywords=tuple(str(keyword) for keyword in item.get("keywords", [])),
                content=None if item.get("content") is None else str(item.get("content")),
                content_fingerprint=(
                    None
                    if item.get("content_fingerprint") is None
                    else str(item.get("content_fingerprint"))
                ),
                fetch_status=str(item.get("fetch_status", "pending")),
                fetch_error=(
                    None
                    if item.get("fetch_error") is None
                    else str(item.get("fetch_error"))
                ),
                extraction_mode=str(item.get("extraction_mode", "unknown")),
                structured_payload={
                    key: value
                    for key, value in dict(item).items()
                    if key
                    not in {
                        "extracted_id",
                        "run_id",
                        "topic_id",
                        "candidate_id",
                        "source_type",
                        "source_name",
                        "title",
                        "url",
                        "published_at",
                        "summary",
                        "keywords",
                        "content",
                        "content_fingerprint",
                        "fetch_status",
                        "fetch_error",
                        "extraction_mode",
                    }
                },
            )
        )

    return tuple(payloads)


def _build_decision_payloads(
    state: dict[str, Any],
) -> tuple[DecisionRecordUpsertData, ...]:
    payloads: list[DecisionRecordUpsertData] = []

    for item in state.get("final_decisions", []):
        candidate_id = str(item["candidate_id"])
        payloads.append(
            DecisionRecordUpsertData(
                decision_id=str(item.get("push_id", f"decision_{candidate_id}")),
                run_id=str(item["run_id"]),
                topic_id=str(item["topic_id"]),
                candidate_id=candidate_id,
                extracted_id=(
                    None
                    if item.get("extracted_id") is None
                    else str(item.get("extracted_id"))
                ),
                source_type=str(item.get("source_type", "unknown")),
                source_name=str(item.get("source_name", "unknown")),
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                published_at=_parse_optional_datetime(item.get("published_at")),
                summary=None if item.get("summary") is None else str(item.get("summary")),
                score=float(item.get("score", 0.0)),
                should_push=bool(item.get("should_push", False)),
                decision_reason=(
                    None
                    if item.get("decision_reason") is None
                    else str(item.get("decision_reason"))
                ),
                decision_payload=dict(item),
            )
        )

    return tuple(payloads)


def evaluate_run_node(
    state: dict[str, Any],
    run_repository: MonitorRunRepositoryProtocol | None = None,
    settings: Settings | None = None,
    history_index_http_client: Any | None = None,
) -> dict[str, Any]:
    _ = run_repository, history_index_http_client
    if not state.get("evaluation_output"):
        state["evaluation_output"] = build_empty_evaluation_output()
    if not state.get("evaluation_output", {}).get("eval_result"):
        append_event(state, "evaluate_run", "Evaluated run metrics and trace completeness.")
        state["eval_result"] = score_run(state)
        state["eval_result"].update(
            build_eval_judge(settings=settings).judge(state["eval_result"])
        )
        state["evaluation_output"]["eval_result"] = dict(state["eval_result"])
    else:
        state["eval_result"] = dict(state["evaluation_output"]["eval_result"])
    state["status"] = "completed"
    return state


def candidate_task_orchestrator_node(
    state: dict[str, Any],
    *,
    gateway: LocalToolGateway,
    run_repository: MonitorRunRepositoryProtocol | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    orchestrator = CandidateTaskOrchestrator(
        fetch_concurrency=(settings.candidate_fetch_concurrency if settings else 2),
        extract_concurrency=(settings.candidate_extract_concurrency if settings else 2),
        evaluate_concurrency=(settings.candidate_evaluate_concurrency if settings else 2),
    )
    extraction_agent = ExtractionAgent(gateway=gateway)
    evaluation_agent = EvaluationAgent(gateway=gateway, settings=settings)

    tasks = orchestrator.build_initial_tasks(state)
    completed_tasks: list[dict[str, Any]] = []
    failed_tasks: list[dict[str, Any]] = []
    queue = list(tasks)
    orchestration_output = build_empty_candidate_task_output()

    append_event(
        state,
        "candidate_task_orchestrator",
        "Started candidate task orchestration.",
        payload={"task_count": len(queue)},
    )

    while queue:
        task = queue.pop(0)
        try:
            if task["stage"] == "fetch":
                result = extraction_agent.run_fetch_task(task, state)
                state["candidate_items"] = list(
                    state.get("retrieval_output", {}).get("candidate_pool", [])
                )
                append_event(
                    state,
                    "fetch_contents",
                    "Fetched candidate content for candidate task.",
                    payload={"candidate_id": str(result["candidate_id"])},
                )
                output_ref = {"fetched_candidate_id": str(result["candidate_id"])}
            elif task["stage"] == "extract":
                result = extraction_agent.run_extract_task(task, state)
                append_event(
                    state,
                    "extract_structured_items",
                    "Extracted structured item for candidate task.",
                    payload={"candidate_id": str(result["candidate_id"])},
                )
                output_ref = {"extracted_candidate_id": str(result["candidate_id"])}
            else:
                result = evaluation_agent.run_evaluate_task(task, state)
                if result.get("task_status") == "skipped":
                    candidate_id = str(
                        result.get("candidate_id", task["candidate_id"])
                    )
                    skipped = dict(task)
                    skipped["status"] = "skipped"
                    skipped["output_ref"] = {
                        "skipped_candidate_id": candidate_id
                    }
                    skipped["error_code"] = None
                    skipped["error_message"] = None
                    skipped["finished_at"] = datetime.now(UTC).isoformat().replace(
                        "+00:00", "Z"
                    )
                    completed_tasks.append(skipped)
                    continue
                output_ref = {"decision_candidate_id": str(result["candidate_id"])}

            completed = orchestrator.mark_task_completed(task, output_ref=output_ref)
            completed_tasks.append(completed)
            queue.extend(orchestrator.build_follow_up_tasks(completed))
        except Exception as exc:
            failed = dict(task)
            failed["status"] = "failed"
            failed["error_code"] = "tool_error"
            failed["error_message"] = str(exc)
            failed["finished_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            failed_tasks.append(failed)
            errors = list(state.get("errors", []))
            errors.append(
                {
                    "tool_name": "candidate_task_orchestrator",
                    "code": "tool_error",
                    "message": str(exc),
                    "details": {
                        "candidate_id": task["candidate_id"],
                        "stage": task["stage"],
                    },
                }
            )
            state["errors"] = errors

    all_tasks = completed_tasks + failed_tasks
    if state.get("extracted_items"):
        scoped_eval_state = {
            **state,
            "evaluation_output": {},
            "scored_items": [],
            "final_decisions": [],
            "decision_reasons": [],
            "push_records": [],
            "eval_result": {},
        }
        evaluation_agent.run(scoped_eval_state)
        state["deduped_items"] = list(scoped_eval_state.get("deduped_items", []))
        state["scored_items"] = list(scoped_eval_state.get("scored_items", []))
        state["final_decisions"] = list(scoped_eval_state.get("final_decisions", []))
        state["decision_reasons"] = list(
            scoped_eval_state.get("decision_reasons", [])
        )
        state["push_records"] = list(scoped_eval_state.get("push_records", []))
        state["tool_results"] = list(scoped_eval_state.get("tool_results", state.get("tool_results", [])))
        state["errors"] = list(scoped_eval_state.get("errors", state.get("errors", [])))
        state["events"] = list(scoped_eval_state.get("events", state.get("events", [])))

    state["candidate_task_plan"] = list(all_tasks)
    state["candidate_task_runtime"] = orchestrator.build_runtime_view(all_tasks)
    state["candidate_task_summary"] = orchestrator.build_summary(all_tasks)
    orchestration_output["tasks"] = list(all_tasks)
    orchestration_output["runtime"] = dict(state["candidate_task_runtime"])
    orchestration_output["summary"] = dict(state["candidate_task_summary"])
    state["candidate_task_output"] = orchestration_output
    existing_evaluation_output = dict(state.get("evaluation_output", {}))
    existing_eval_result = dict(existing_evaluation_output.get("eval_result", {}))
    if existing_eval_result:
        state["eval_result"] = dict(existing_eval_result)
    else:
        state["eval_result"] = score_run(state)
        state["eval_result"].update(
            build_eval_judge(settings=settings).judge(state["eval_result"])
        )
    state["evaluation_output"] = {
        **build_empty_evaluation_output(),
        **existing_evaluation_output,
        "deduped_items": list(state.get("deduped_items", [])),
        "scored_items": list(state.get("scored_items", [])),
        "final_decisions": list(state.get("final_decisions", [])),
        "decision_reasons": list(state.get("decision_reasons", [])),
        "push_records": list(state.get("push_records", [])),
        "eval_result": dict(state["eval_result"]),
    }

    if (
        run_repository is not None
        and all_tasks
        and hasattr(run_repository, "create_candidate_task_records")
    ):
        run_repository.create_candidate_task_records(
            tuple(
                CandidateTaskRecordCreateData(
                    task_id=str(task["task_id"]),
                    run_id=str(task["run_id"]),
                    candidate_id=str(task["candidate_id"]),
                    stage=str(task["stage"]),
                    status=str(task["status"]),
                    attempt=int(task.get("attempt", 1)),
                    max_attempts=int(task.get("max_attempts", 1)),
                    depends_on_task_ids=tuple(
                        str(item) for item in task.get("depends_on_task_ids", [])
                    ),
                    input_ref=dict(task.get("input_ref", {})),
                    output_ref=dict(task.get("output_ref", {})),
                    error_code=(
                        None if task.get("error_code") is None else str(task["error_code"])
                    ),
                    error_message=(
                        None
                        if task.get("error_message") is None
                        else str(task["error_message"])
                    ),
                    started_at=None,
                    finished_at=None,
                )
                for task in all_tasks
            )
        )

    append_event(
        state,
        "candidate_task_orchestrator",
        "Completed candidate task orchestration.",
        payload=dict(state["candidate_task_summary"]),
    )
    return state


def supervisor_finalize_node(
    state: dict[str, Any],
    run_repository: MonitorRunRepositoryProtocol | None = None,
    settings: Settings | None = None,
    history_index_http_client: Any | None = None,
) -> dict[str, Any]:
    planner_output = dict(state.get("planner_output", {}))
    retrieval_output = dict(state.get("retrieval_output", {}))
    extraction_output = dict(state.get("extraction_output", {}))
    evaluation_output = dict(state.get("evaluation_output", {}))

    planner_expanded_queries = planner_output.get("expanded_queries")
    if planner_expanded_queries:
        state["expanded_queries"] = list(planner_expanded_queries)
    state["candidate_items"] = list(
        retrieval_output.get("candidate_pool", state.get("candidate_items", []))
    )
    state["fetched_contents"] = list(
        extraction_output.get("fetched_contents", state.get("fetched_contents", []))
    )
    state["extracted_items"] = list(
        extraction_output.get("evidence_items", state.get("extracted_items", []))
    )
    state["deduped_items"] = list(
        evaluation_output.get("deduped_items", state.get("deduped_items", []))
    )
    state["scored_items"] = list(
        evaluation_output.get("scored_items", state.get("scored_items", []))
    )
    state["final_decisions"] = list(
        evaluation_output.get("final_decisions", state.get("final_decisions", []))
    )
    state["decision_reasons"] = list(
        evaluation_output.get("decision_reasons", state.get("decision_reasons", []))
    )
    state["push_records"] = list(
        evaluation_output.get("push_records", state.get("push_records", []))
    )
    state["eval_result"] = dict(
        evaluation_output.get("eval_result", state.get("eval_result", {}))
    )
    integration_runtime = dict(state.get("integration_runtime", {}))
    if not integration_runtime:
        integration_runtime = build_integration_runtime(
            settings=settings,
            tool_results=list(state.get("tool_results", [])),
            fetched_contents=list(state.get("fetched_contents", [])),
        )
    state["integration_runtime"] = integration_runtime
    state["status"] = "completed"

    if state.get("run_context"):
        state["run_context"]["status"] = "completed"
        state["run_context"]["errors"] = list(state.get("errors", []))
        state["run_context"]["events"] = list(state.get("events", []))
    if state.get("business_memory"):
        state["business_memory"]["push_history"] = list(state.get("push_history", []))

    if run_repository is not None:
        state["extracted_records"] = run_repository.upsert_extracted_item_records(
            _build_extracted_item_payloads(state)
        )
        state["decision_records"] = run_repository.upsert_decision_records(
            _build_decision_payloads(state)
        )
        state["candidate_records"] = run_repository.upsert_candidate_records(
            _build_candidate_payloads(state)
        )
        history_index = build_history_index(
            settings=settings,
            http_client=history_index_http_client,
        )
        try:
            state["history_index_result"] = history_index.index_candidates(
                list(state["candidate_records"])
            )
            if state["history_index_result"].get("provider") != "none":
                search_failed = False
                query = _build_history_index_query(state)
                if query:
                    exclusions = _build_history_index_exclusions(state)
                    try:
                        search_result = history_index.search_candidates(
                            query,
                            top_k=3,
                            exclude_run_id=exclusions["exclude_run_id"],
                            exclude_candidate_ids=exclusions["exclude_candidate_ids"],
                        )
                        state["history_index_result"]["search"] = (
                            _build_history_index_search_evidence(search_result)
                        )
                    except Exception as exc:
                        search_failed = True
                        state["history_index_result"]["search"] = (
                            _build_history_index_search_failure_evidence(
                                provider=state["history_index_result"].get("provider"),
                                query=query,
                                error_message=str(exc),
                            )
                        )
                        errors = list(state.get("errors", []))
                        errors.append(
                            {
                                "tool_name": "history_index",
                                "code": "history_index_search_failed",
                                "message": str(exc),
                                "details": {
                                    "provider": state["history_index_result"].get(
                                        "provider"
                                    ),
                                    "query": query,
                                },
                            }
                        )
                        state["errors"] = errors
                        append_event(
                            state,
                            "index_history",
                            "Failed to search candidate history projection.",
                            event_type="node_failed",
                            payload={
                                "provider": state["history_index_result"].get(
                                    "provider"
                                ),
                                "query": query,
                                "error_message": str(exc),
                            },
                        )
                if not search_failed:
                    append_event(
                        state,
                        "index_history",
                        "Indexed candidate history projection.",
                        payload={
                            "provider": state["history_index_result"].get("provider"),
                            "indexed_count": state["history_index_result"].get(
                                "indexed_count",
                                0,
                            ),
                        },
                    )
        except Exception as exc:
            errors = list(state.get("errors", []))
            errors.append(
                {
                    "tool_name": "history_index",
                    "code": "history_index_failed",
                    "message": str(exc),
                    "details": {
                        "provider": (
                            settings.history_index_provider if settings else None
                        )
                    },
                }
            )
            state["errors"] = errors
            append_event(
                state,
                "index_history",
                "Failed to index candidate history projection.",
                event_type="node_failed",
                payload={
                    "provider": settings.history_index_provider if settings else None,
                    "error_message": str(exc),
                },
            )
        run_repository.create_run_events(
            tuple(
                RunEventCreateData(
                    run_id=str(event["run_id"]),
                    topic_id=str(event["topic_id"]),
                    event_type=str(event["event_type"]),
                    node=str(event["node"]),
                    message=str(event["message"]),
                    payload=dict(event.get("payload", {})),
                    elapsed_ms=(
                        None
                        if event.get("elapsed_ms") is None
                        else int(event["elapsed_ms"])
                    ),
                )
                for event in state.get("events", [])
            )
        )
        if state.get("eval_result"):
            state["eval_result"] = run_repository.create_eval_result(
                EvalResultCreateData(
                    run_id=str(state["run_id"]),
                    topic_id=str(state["topic_id"]),
                    retrieved_count=int(state["eval_result"]["retrieved_count"]),
                    deduped_count=int(state["eval_result"]["deduped_count"]),
                    dedup_rate=float(state["eval_result"]["dedup_rate"]),
                    push_count=int(state["eval_result"]["push_count"]),
                    duplicate_push_count=int(state["eval_result"]["duplicate_push_count"]),
                    tool_success_rate=float(state["eval_result"]["tool_success_rate"]),
                    fetch_success_rate=float(state["eval_result"]["fetch_success_rate"]),
                    trace_completeness=float(state["eval_result"]["trace_completeness"]),
                    raw_summary_count=int(state["eval_result"]["raw_summary_count"]),
                    browser_fallback_count=int(
                        state["eval_result"]["browser_fallback_count"]
                    ),
                    provider_fallback_count=int(
                        state["eval_result"]["provider_fallback_count"]
                    ),
                    judge_mode=str(state["eval_result"]["judge_mode"]),
                    judge_score=float(state["eval_result"]["judge_score"]),
                    judge_reason=str(state["eval_result"]["judge_reason"]),
                    judge_issues=tuple(state["eval_result"].get("judge_issues", [])),
                    suggestions=tuple(state["eval_result"].get("suggestions", [])),
                )
            )
            if state.get("evaluation_output"):
                state["evaluation_output"]["eval_result"] = dict(state["eval_result"])
        run_repository.upsert_monitor_run(_build_monitor_run_payload(state))

    return state
