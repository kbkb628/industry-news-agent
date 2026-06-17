from __future__ import annotations

from typing import Any

from app.eval.eval_cases import build_eval_suggestions

REQUIRED_TRACE_NODES = {
    "load_topic",
    "retrieve_business_context",
    "expand_queries",
    "plan_sources",
    "retrieve_candidates",
    "fetch_contents",
    "extract_structured_items",
    "deduplicate_items",
    "score_items",
    "decide_push",
    "persist_push_records",
    "evaluate_run",
}


def score_run(state: dict[str, Any]) -> dict[str, Any]:
    retrieved_count = len(state.get("candidate_items", []))
    deduped_count = len(state.get("deduped_items", []))
    push_count = len(state.get("push_records", []))

    observed_nodes = {
        str(event.get("node", ""))
        for event in state.get("events", [])
        if event.get("node")
    }
    tool_results = list(state.get("tool_results", []))
    fetched_contents = list(state.get("fetched_contents", []))
    extracted_items = list(state.get("extracted_items", []))
    duplicate_push_count = sum(
        1
        for decision in state.get("final_decisions", [])
        if "canonical_url already exists" in str(decision.get("decision_reason", ""))
        or "within cooldown" in str(decision.get("decision_reason", ""))
    )

    tool_success_rate = 1.0
    if tool_results:
        successful_tools = sum(1 for item in tool_results if item.get("success"))
        tool_success_rate = round(successful_tools / len(tool_results), 2)

    fetch_success_rate = 0.0
    if fetched_contents:
        fetched_ok = sum(
            1 for item in fetched_contents if item.get("fetch_status") == "fetched"
        )
        fetch_success_rate = round(fetched_ok / len(fetched_contents), 2)

    raw_summary_count = sum(
        1 for item in extracted_items if item.get("extraction_mode") == "raw_summary"
    )
    browser_fallback_count = sum(
        1
        for item in fetched_contents
        if item.get("fetch_method") == "browser_fallback"
    ) + sum(
        1
        for item in tool_results
        if item.get("metadata", {}).get("used_browser_fallback") is True
    )
    provider_fallback_count = sum(
        1
        for item in tool_results
        if item.get("metadata", {}).get("used_fallback") is True
    )

    trace_completeness = round(
        len(REQUIRED_TRACE_NODES & observed_nodes) / len(REQUIRED_TRACE_NODES),
        2,
    )
    dedup_rate = 0.0
    if retrieved_count:
        dedup_rate = round((retrieved_count - deduped_count) / retrieved_count, 2)

    return {
        "retrieved_count": retrieved_count,
        "deduped_count": deduped_count,
        "dedup_rate": dedup_rate,
        "push_count": push_count,
        "duplicate_push_count": duplicate_push_count,
        "tool_success_rate": tool_success_rate,
        "fetch_success_rate": fetch_success_rate,
        "trace_completeness": trace_completeness,
        "raw_summary_count": raw_summary_count,
        "browser_fallback_count": browser_fallback_count,
        "provider_fallback_count": provider_fallback_count,
        "suggestions": build_eval_suggestions(
            push_count=push_count,
            fetch_success_rate=fetch_success_rate,
            trace_completeness=trace_completeness,
        ),
    }
