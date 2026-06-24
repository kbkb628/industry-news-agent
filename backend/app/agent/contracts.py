from __future__ import annotations

from typing import Any, TypedDict


class RunContext(TypedDict, total=False):
    run_id: str
    topic_id: str
    topic: dict[str, Any]
    trigger: str
    status: str
    errors: list[dict[str, Any]]
    events: list[dict[str, Any]]


class BusinessMemory(TypedDict, total=False):
    seed_keywords: list[str]
    business_context: dict[str, Any]
    push_history: list[dict[str, Any]]
    trusted_sources: list[str]
    degradation_hints: list[str]


class PlannerOutput(TypedDict, total=False):
    expanded_queries: list[str]
    query_plan: list[dict[str, Any]]
    source_plan: list[dict[str, Any]]
    retrieval_strategy: dict[str, Any]
    planning_reasons: list[str]


class RetrievalOutput(TypedDict, total=False):
    candidate_pool: list[dict[str, Any]]
    source_coverage: list[dict[str, Any]]
    retrieval_failures: list[dict[str, Any]]
    provider_fallbacks: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]


class ExtractionOutput(TypedDict, total=False):
    fetched_contents: list[dict[str, Any]]
    evidence_items: list[dict[str, Any]]
    extraction_failures: list[dict[str, Any]]
    content_fallbacks: list[dict[str, Any]]


class EvaluationOutput(TypedDict, total=False):
    deduped_items: list[dict[str, Any]]
    scored_items: list[dict[str, Any]]
    final_decisions: list[dict[str, Any]]
    decision_reasons: list[str]
    push_records: list[dict[str, Any]]
    eval_result: dict[str, Any]


class CandidateTaskRecord(TypedDict, total=False):
    task_id: str
    run_id: str
    candidate_id: str
    stage: str
    status: str
    attempt: int
    max_attempts: int
    depends_on_task_ids: list[str]
    input_ref: dict[str, Any]
    output_ref: dict[str, Any]
    error_code: str | None
    error_message: str | None
    started_at: str | None
    finished_at: str | None


class CandidateTaskRuntime(TypedDict, total=False):
    ready_count: int
    in_progress_count: int
    completed_count: int
    failed_count: int
    skipped_count: int
    stage_slots: dict[str, dict[str, int]]


class CandidateTaskSummary(TypedDict, total=False):
    task_count: int
    completed_count: int
    failed_count: int
    skipped_count: int
    fetch_completed_count: int
    extract_completed_count: int
    evaluate_completed_count: int


def build_empty_run_context(*, run_id: str, topic_id: str) -> RunContext:
    return {
        "run_id": run_id,
        "topic_id": topic_id,
        "trigger": "manual",
        "status": "created",
        "errors": [],
        "events": [],
    }


def build_empty_business_memory() -> BusinessMemory:
    return {
        "seed_keywords": [],
        "business_context": {},
        "push_history": [],
        "trusted_sources": [],
        "degradation_hints": [],
    }


def build_empty_planner_output() -> PlannerOutput:
    return {
        "expanded_queries": [],
        "query_plan": [],
        "source_plan": [],
        "retrieval_strategy": {},
        "planning_reasons": [],
    }


def build_empty_retrieval_output() -> RetrievalOutput:
    return {
        "candidate_pool": [],
        "source_coverage": [],
        "retrieval_failures": [],
        "provider_fallbacks": [],
        "tool_results": [],
    }


def build_empty_extraction_output() -> ExtractionOutput:
    return {
        "fetched_contents": [],
        "evidence_items": [],
        "extraction_failures": [],
        "content_fallbacks": [],
    }


def build_empty_evaluation_output() -> EvaluationOutput:
    return {
        "deduped_items": [],
        "scored_items": [],
        "final_decisions": [],
        "decision_reasons": [],
        "push_records": [],
        "eval_result": {},
    }


def build_empty_candidate_task_output() -> dict[str, Any]:
    return {
        "tasks": [],
        "runtime": {
            "ready_count": 0,
            "in_progress_count": 0,
            "completed_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "stage_slots": {
                "fetch": {"limit": 0, "in_progress": 0},
                "extract": {"limit": 0, "in_progress": 0},
                "evaluate": {"limit": 0, "in_progress": 0},
            },
        },
        "summary": {
            "task_count": 0,
            "completed_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "fetch_completed_count": 0,
            "extract_completed_count": 0,
            "evaluate_completed_count": 0,
        },
    }
