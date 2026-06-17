from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from app.agent.nodes import (
    retrieve_business_context_node,
    supervisor_bootstrap_node,
    supervisor_finalize_node,
)
from app.agent.state import MonitorState
from app.agent.evaluation_agent import EvaluationAgent
from app.agent.extraction_agent import ExtractionAgent
from app.agent.planner_agent import PlannerAgent
from app.agent.retrieval_agent import RetrievalAgent
from app.core.config import Settings
from app.llm.base import BaseLLMClient
from app.llm.mock_client import MockLLM
from app.mcp.gateway import ToolGateway
from app.mcp.local_gateway import LocalToolGateway
from app.mcp.onesearch_gateway import OneSearchMCPGateway
from app.storage.repository import MonitorRunRepositoryProtocol
from app.tools.registry import build_default_tool_registry


def _build_default_gateway(
    llm: BaseLLMClient,
    settings: Settings | None,
    notification_http_client: Any | None = None,
) -> ToolGateway:
    local_gateway = LocalToolGateway()
    build_default_tool_registry(
        llm=llm,
        settings=settings,
        notification_http_client=notification_http_client,
    ).register_into(local_gateway)
    if (
        settings is None
        or settings.mcp_gateway_provider != "onesearch"
        or not settings.onesearch_base_url
    ):
        return local_gateway

    return OneSearchMCPGateway(
        base_url=settings.onesearch_base_url,
        fallback_gateway=local_gateway,
        timeout_seconds=settings.onesearch_timeout_seconds,
        max_results=settings.onesearch_max_results,
    )


def build_monitor_graph(
    *,
    llm: BaseLLMClient | None = None,
    gateway: ToolGateway | None = None,
    run_repository: MonitorRunRepositoryProtocol | None = None,
    settings: Settings | None = None,
    history_index_http_client: Any | None = None,
    notification_http_client: Any | None = None,
):
    resolved_llm = llm or MockLLM()
    resolved_gateway = gateway or _build_default_gateway(
        resolved_llm,
        settings,
        notification_http_client,
    )

    graph = StateGraph(MonitorState)
    graph.add_node(
        "supervisor_bootstrap",
        lambda state: supervisor_bootstrap_node(state, run_repository),
    )
    graph.add_node(
        "planner_agent",
        lambda state: _run_planner_stage(
            state,
            llm=resolved_llm,
        ),
    )
    graph.add_node(
        "retrieval_agent",
        lambda state: RetrievalAgent(gateway=resolved_gateway).run(state),
    )
    graph.add_node(
        "extraction_agent",
        lambda state: _run_extraction_stage(state, gateway=resolved_gateway),
    )
    graph.add_node(
        "evaluation_agent",
        lambda state: EvaluationAgent(
            gateway=resolved_gateway,
            settings=settings,
        ).run(state),
    )
    graph.add_node(
        "supervisor_finalize",
        lambda state: _run_supervisor_finalize_stage(
            state,
            run_repository,
            resolved_gateway,
            settings,
            history_index_http_client,
        ),
    )

    graph.set_entry_point("supervisor_bootstrap")
    graph.add_edge("supervisor_bootstrap", "planner_agent")
    graph.add_edge("planner_agent", "retrieval_agent")
    graph.add_edge("retrieval_agent", "extraction_agent")
    graph.add_edge("extraction_agent", "evaluation_agent")
    graph.add_edge("evaluation_agent", "supervisor_finalize")
    graph.add_edge("supervisor_finalize", END)

    return graph.compile()


def _run_planner_stage(
    state: dict[str, Any],
    *,
    llm: BaseLLMClient,
) -> dict[str, Any]:
    retrieve_business_context_node(state)
    state["planner_output"] = state.get("planner_output", {})
    return PlannerAgent(llm=llm).run(state)


def _run_extraction_stage(
    state: dict[str, Any],
    *,
    gateway: ToolGateway,
) -> dict[str, Any]:
    agent = ExtractionAgent(gateway=gateway)
    agent.fetch_contents(state)
    agent.extract_evidence(state)
    return state


def _run_supervisor_finalize_stage(
    state: dict[str, Any],
    run_repository: MonitorRunRepositoryProtocol | None,
    gateway: ToolGateway,
    settings: Settings | None,
    history_index_http_client: Any | None,
) -> dict[str, Any]:
    from app.agent.nodes import persist_push_records_node

    persist_push_records_node(
        state,
        run_repository=run_repository,
        gateway=gateway,
    )
    state = supervisor_finalize_node(
        state,
        run_repository=run_repository,
        settings=settings,
        history_index_http_client=history_index_http_client,
    )
    return state
