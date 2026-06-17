from __future__ import annotations

from typing import Any, TypedDict


class MonitorState(TypedDict, total=False):
    run_id: str
    topic_id: str
    trigger: str
    topic: dict[str, Any]
    seed_keywords: list[str]
    expanded_queries: list[str]
    business_context: dict[str, Any]
    source_plan: list[str]
    candidate_items: list[dict[str, Any]]
    fetched_contents: list[dict[str, Any]]
    extracted_items: list[dict[str, Any]]
    deduped_items: list[dict[str, Any]]
    scored_items: list[dict[str, Any]]
    final_decisions: list[dict[str, Any]]
    decision_reasons: list[str]
    push_records: list[dict[str, Any]]
    push_history: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    eval_result: dict[str, Any]
    events: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    status: str
