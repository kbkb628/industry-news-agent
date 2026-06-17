from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        lowered = normalized.lower()
        if not normalized or lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(normalized)
    return deduped


def build_query_plan(expanded_queries: Iterable[str]) -> list[dict[str, Any]]:
    unique_queries: list[str] = []
    seen: set[str] = set()
    for query in expanded_queries:
        normalized = str(query).strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_queries.append(normalized)

    return [
        {
            "query": query,
            "priority": index + 1,
            "intent": "monitor_industry_news",
        }
        for index, query in enumerate(unique_queries)
    ]


def build_source_plan(topic: dict[str, Any]) -> list[str]:
    _ = topic
    return ["rss_fetch", "mock_search"]


def build_structured_source_plan(
    topic: dict[str, Any],
    *,
    trusted_sources: Iterable[str],
    push_history: Iterable[dict[str, Any]],
    business_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    topic_trusted_sources = topic.get("trusted_sources", [])
    combined_trusted_sources = _dedupe_strings([*topic_trusted_sources, *trusted_sources])
    history_count = sum(1 for _ in push_history)
    context_documents = list((business_context or {}).get("documents", []))
    has_trusted_sources = bool(combined_trusted_sources)
    has_context = bool(context_documents)
    search_priority = 1 if not has_trusted_sources and not has_context else 2
    rss_priority = 2 if search_priority == 1 else 1

    source_plan = [
        {
            "tool_name": "mock_search",
            "priority": search_priority,
            "reason": (
                "Search leads when trusted-source memory is sparse and recall needs widening."
                if search_priority == 1
                else "Search complements feed coverage for non-RSS discovery."
            ),
            "history_signal": {"prior_push_count": history_count},
            "context_signal": {"document_count": len(context_documents)},
        },
        {
            "tool_name": "rss_fetch",
            "priority": rss_priority,
            "reason": "Trusted feeds are stable and low-cost for repeat monitoring.",
            "trusted_sources": combined_trusted_sources,
        },
    ]
    return sorted(source_plan, key=lambda item: int(item["priority"]))


def build_retrieval_strategy(
    source_plan: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    ordered_source_plan = list(source_plan)
    ordered_tools = [
        str(item.get("tool_name", ""))
        for item in ordered_source_plan
        if item.get("tool_name")
    ]
    mode = "search_first" if ordered_tools and ordered_tools[0] == "mock_search" else "rss_first"
    return {
        "mode": mode,
        "ordered_tools": ordered_tools,
        "fallback_policy": "continue_on_source_gap",
    }


def build_planning_reasons(
    *,
    topic_name: str,
    business_context: dict[str, Any],
    trusted_sources: Iterable[str],
    push_history: Iterable[dict[str, Any]],
) -> list[str]:
    document_count = len(list(business_context.get("documents", [])))
    trusted_source_count = len([source for source in trusted_sources if str(source).strip()])
    history_count = sum(1 for _ in push_history)

    return [
        f"Topic '{topic_name}' requires recall across feed and search sources.",
        f"Loaded {document_count} business-context documents into planning.",
        f"Trusted source bias applied to {trusted_source_count} domains.",
        f"Considered {history_count} historical push records to avoid narrow planning.",
    ]
