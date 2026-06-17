from __future__ import annotations

from typing import Any

from app.agent.contracts import build_empty_evaluation_output
from app.eval.judge import build_eval_judge
from app.eval.rule_scorer import score_run
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


class EvaluationAgent:
    def __init__(
        self,
        *,
        gateway: ToolGateway,
        settings: Any | None = None,
    ) -> None:
        self.gateway = gateway
        self.settings = settings

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        topic = dict(
            state.get("topic")
            or state.get("run_context", {}).get("topic", {})
            or {}
        )
        run_id = str(
            state.get("run_id")
            or state.get("run_context", {}).get("run_id", "")
        )
        extraction_output = dict(state.get("extraction_output", {}))
        evidence_items = list(
            extraction_output.get("evidence_items", state.get("extracted_items", []))
        )
        push_history = list(
            state.get("business_memory", {}).get(
                "push_history",
                state.get("push_history", []),
            )
        )

        evaluation_output = build_empty_evaluation_output()

        deduplicate_response = _call_tool(
            state,
            self.gateway,
            "deduplicate_items",
            articles=evidence_items,
        )
        deduped_items = list(dict(deduplicate_response.data or {}).get("articles", []))
        append_event(
            state,
            "deduplicate_items",
            "Deduplicated extracted article items.",
            payload={
                "count": len(deduped_items),
                "dropped_candidate_ids": list(
                    dict(deduplicate_response.data or {}).get("dropped_candidate_ids", [])
                ),
            },
        )

        score_response = _call_tool(
            state,
            self.gateway,
            "score_candidate",
            topic=topic,
            articles=deduped_items,
        )
        scored_items = list(dict(score_response.data or {}).get("articles", []))
        append_event(
            state,
            "score_items",
            "Scored candidate items against topic rules.",
            payload={"count": len(scored_items)},
        )

        decide_response = _call_tool(
            state,
            self.gateway,
            "decide_push",
            run_id=run_id,
            topic=topic,
            articles=scored_items,
            push_history=push_history,
        )
        final_decisions = list(dict(decide_response.data or {}).get("pushes", []))
        decision_reasons = [
            str(item.get("decision_reason", "")) for item in final_decisions
        ]
        append_event(
            state,
            "decide_push",
            "Calculated push decisions for scored candidates.",
            payload={
                "count": len(final_decisions),
                "push_count": dict(decide_response.data or {}).get("push_count", 0),
            },
        )

        push_records = [
            dict(item) for item in final_decisions if item.get("should_push")
        ]

        # Mirror the stage outputs before scoring so eval metrics reflect the stage outputs.
        state["deduped_items"] = deduped_items
        state["scored_items"] = scored_items
        state["final_decisions"] = final_decisions
        state["decision_reasons"] = decision_reasons
        state["push_records"] = push_records

        eval_result = score_run(state)
        eval_result.update(build_eval_judge(settings=self.settings).judge(eval_result))
        append_event(
            state,
            "evaluate_run",
            "Evaluated run metrics and trace completeness.",
        )

        evaluation_output.update(
            {
                "deduped_items": deduped_items,
                "scored_items": scored_items,
                "final_decisions": final_decisions,
                "decision_reasons": decision_reasons,
                "push_records": push_records,
                "eval_result": eval_result,
            }
        )
        state["evaluation_output"] = evaluation_output
        state["eval_result"] = eval_result

        return state
