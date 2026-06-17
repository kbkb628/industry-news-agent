from __future__ import annotations

from typing import Any

from app.agent.contracts import build_empty_retrieval_output
from app.mcp.gateway import ToolGateway
from app.observability.event_logger import append_event
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
    if response.error is None:
        return
    errors = list(state.get("errors", []))
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
    gateway: ToolGateway,
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


class RetrievalAgent:
    def __init__(self, *, gateway: ToolGateway) -> None:
        self.gateway = gateway

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        planner_output = dict(state.get("planner_output", {}))
        source_plan = list(planner_output.get("source_plan", []))
        topic = dict(
            state.get("topic")
            or state.get("run_context", {}).get("topic", {})
            or {}
        )
        run_id = str(
            state.get("run_id")
            or state.get("run_context", {}).get("run_id", "")
        )

        retrieval_output = build_empty_retrieval_output()
        candidate_pool: list[dict[str, Any]] = []
        source_coverage: list[dict[str, Any]] = []
        retrieval_failures: list[dict[str, Any]] = []
        provider_fallbacks: list[dict[str, Any]] = []

        for planned_source in source_plan:
            tool_name = str(planned_source.get("tool_name", "")).strip()
            if not tool_name:
                continue

            response = _call_tool(
                state,
                self.gateway,
                tool_name,
                run_id=run_id,
                topic=topic,
            )
            payload = dict(response.data or {})
            candidates = list(payload.get("candidates", []))
            candidate_pool.extend(candidates)

            source_coverage.append(
                {
                    "tool_name": tool_name,
                    "candidate_count": len(candidates),
                    "provider": response.metadata.get("provider", tool_name),
                }
            )

            if response.metadata.get("used_fallback"):
                fallback_record = {
                    "tool_name": response.tool_name,
                    "provider": response.metadata.get("provider"),
                    "fallback_provider": response.metadata.get("fallback_provider"),
                    "fallback_reason": response.metadata.get("fallback_reason"),
                }
                provider_fallbacks.append(fallback_record)
                append_event(
                    state,
                    "retrieve_candidates",
                    "Used fallback search provider for candidate retrieval.",
                    event_type="fallback_used",
                    payload=fallback_record,
                )

        retrieval_output.update(
            {
                "candidate_pool": candidate_pool,
                "source_coverage": source_coverage,
                "retrieval_failures": retrieval_failures,
                "provider_fallbacks": provider_fallbacks,
                "tool_results": list(state.get("tool_results", [])),
            }
        )

        state["retrieval_output"] = retrieval_output

        # Keep legacy fields populated until stage-level finalization takes over.
        state["candidate_items"] = candidate_pool

        return state
