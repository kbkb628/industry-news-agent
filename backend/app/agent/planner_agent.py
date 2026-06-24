from __future__ import annotations

from typing import Any

from app.agent.contracts import build_empty_planner_output
from app.agent.planner import (
    build_planning_reasons,
    build_query_plan,
    build_retrieval_strategy,
    build_structured_source_plan,
)
from app.llm.base import BaseLLMClient


def _dedupe_preserve_order(values: list[str]) -> list[str]:
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


class PlannerAgent:
    def __init__(self, *, llm: BaseLLMClient) -> None:
        self.llm = llm

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        topic = dict(state.get("topic", {}))
        business_memory = dict(state.get("business_memory", {}))
        planner_output = build_empty_planner_output()

        topic_name = str(topic.get("name", ""))
        seed_keywords = list(business_memory.get("seed_keywords", []))
        trusted_sources = list(
            business_memory.get("trusted_sources", topic.get("trusted_sources", []))
        )
        push_history = list(business_memory.get("push_history", []))
        business_context = dict(business_memory.get("business_context", {}))
        semantic_memory = dict(business_context.get("semantic_memory", {}))
        semantic_topic_keywords = list(semantic_memory.get("topic_keywords", []))

        expanded_queries = list(state.get("expanded_queries", []))
        if not expanded_queries:
            expanded_queries = self.llm.expand_keywords(
                topic_name=topic_name,
                seed_keywords=_dedupe_preserve_order(
                    [*seed_keywords, *semantic_topic_keywords]
                ),
            )
        expanded_queries = _dedupe_preserve_order(
            [*expanded_queries, *semantic_topic_keywords]
        )
        query_plan = build_query_plan(expanded_queries)
        source_plan = build_structured_source_plan(
            topic,
            trusted_sources=trusted_sources,
            push_history=push_history,
            business_context=business_context,
        )
        retrieval_strategy = build_retrieval_strategy(source_plan)
        planning_reasons = build_planning_reasons(
            topic_name=topic_name,
            business_context=business_context,
            trusted_sources=trusted_sources,
            push_history=push_history,
        )

        planner_output.update(
            {
                "expanded_queries": expanded_queries,
                "query_plan": query_plan,
                "source_plan": source_plan,
                "retrieval_strategy": retrieval_strategy,
                "planning_reasons": planning_reasons,
            }
        )

        state["planner_output"] = planner_output

        # Keep legacy fields populated until the stage-level graph migration lands.
        state["expanded_queries"] = expanded_queries
        state["source_plan"] = [
            str(item["tool_name"])
            for item in source_plan
            if item.get("tool_name") is not None
        ]

        return state
