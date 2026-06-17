from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from app.agent.nodes import (
    decide_push_node,
    deduplicate_items_node,
    evaluate_run_node,
    expand_queries_node,
    extract_structured_items_node,
    fetch_contents_node,
    load_topic_node,
    persist_push_records_node,
    plan_sources_node,
    retrieve_business_context_node,
    retrieve_candidates_node,
    score_items_node,
)
from app.agent.state import MonitorState
from app.core.config import Settings
from app.llm.base import BaseLLMClient
from app.llm.mock_client import MockLLM
from app.mcp.local_gateway import LocalToolGateway
from app.storage.repository import MonitorRunRepositoryProtocol
from app.tools.registry import build_default_tool_registry


def _build_default_gateway(
    llm: BaseLLMClient,
    settings: Settings | None,
) -> LocalToolGateway:
    gateway = LocalToolGateway()
    build_default_tool_registry(llm=llm, settings=settings).register_into(gateway)
    return gateway


def build_monitor_graph(
    *,
    llm: BaseLLMClient | None = None,
    gateway: LocalToolGateway | None = None,
    run_repository: MonitorRunRepositoryProtocol | None = None,
    settings: Settings | None = None,
    history_index_http_client: Any | None = None,
):
    resolved_llm = llm or MockLLM()
    resolved_gateway = gateway or _build_default_gateway(resolved_llm, settings)

    graph = StateGraph(MonitorState)
    graph.add_node(
        "load_topic_node",
        lambda state: load_topic_node(state, run_repository),
    )
    graph.add_node("retrieve_business_context_node", retrieve_business_context_node)
    graph.add_node(
        "expand_queries_node",
        lambda state: expand_queries_node(state, resolved_llm),
    )
    graph.add_node("plan_sources_node", plan_sources_node)
    graph.add_node(
        "retrieve_candidates_node",
        lambda state: retrieve_candidates_node(state, resolved_gateway),
    )
    graph.add_node(
        "fetch_contents_node",
        lambda state: fetch_contents_node(state, resolved_gateway),
    )
    graph.add_node(
        "extract_structured_items_node",
        lambda state: extract_structured_items_node(state, resolved_gateway),
    )
    graph.add_node(
        "deduplicate_items_node",
        lambda state: deduplicate_items_node(state, resolved_gateway),
    )
    graph.add_node(
        "score_items_node",
        lambda state: score_items_node(state, resolved_gateway),
    )
    graph.add_node(
        "decide_push_node",
        lambda state: decide_push_node(state, resolved_gateway),
    )
    graph.add_node(
        "persist_push_records_node",
        lambda state: persist_push_records_node(state, run_repository),
    )
    graph.add_node(
        "evaluate_run_node",
        lambda state: evaluate_run_node(
            state,
            run_repository,
            settings,
            history_index_http_client,
        ),
    )

    graph.set_entry_point("load_topic_node")
    graph.add_edge("load_topic_node", "retrieve_business_context_node")
    graph.add_edge("retrieve_business_context_node", "expand_queries_node")
    graph.add_edge("expand_queries_node", "plan_sources_node")
    graph.add_edge("plan_sources_node", "retrieve_candidates_node")
    graph.add_edge("retrieve_candidates_node", "fetch_contents_node")
    graph.add_edge("fetch_contents_node", "extract_structured_items_node")
    graph.add_edge("extract_structured_items_node", "deduplicate_items_node")
    graph.add_edge("deduplicate_items_node", "score_items_node")
    graph.add_edge("score_items_node", "decide_push_node")
    graph.add_edge("decide_push_node", "persist_push_records_node")
    graph.add_edge("persist_push_records_node", "evaluate_run_node")
    graph.add_edge("evaluate_run_node", END)

    return graph.compile()
