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


def _build_rag_guidance_metrics(scored_items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "rag_guidance_applied_count": sum(
            1 for item in scored_items if int(item.get("rag_guidance_hits", 0)) > 0
        ),
        "trusted_source_match_count": sum(
            1 for item in scored_items if bool(item.get("trusted_source_match"))
        ),
        "rule_guidance_hits": sum(
            int(item.get("rule_guidance_hits", 0)) for item in scored_items
        ),
    }


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
        business_context = dict(
            state.get("business_memory", {}).get(
                "business_context",
                state.get("business_context", {}),
            )
            or {}
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
            **({"business_context": business_context} if business_context else {}),
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
        eval_result.update(_build_rag_guidance_metrics(scored_items))
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

    @staticmethod
    def _merge_candidate_item(
        items: list[dict[str, Any]],
        candidate: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidate_id = str(candidate.get("candidate_id", ""))
        merged: list[dict[str, Any]] = []
        replaced = False
        for item in items:
            if str(item.get("candidate_id", "")) == candidate_id:
                merged.append(dict(candidate))
                replaced = True
            else:
                merged.append(dict(item))
        if not replaced:
            merged.append(dict(candidate))
        return merged

    def run_evaluate_task(
        self,
        task: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        candidate_id = str(task["candidate_id"])
        extracted_items = list(state.get("extracted_items", []))
        deduplicate_response = _call_tool(
            state,
            self.gateway,
            "deduplicate_items",
            articles=extracted_items,
        )
        deduped_existing = list(dict(deduplicate_response.data or {}).get("articles", []))
        if deduped_existing and not any(
            str(item.get("candidate_id")) == candidate_id for item in deduped_existing
        ):
            return {
                "candidate_id": candidate_id,
                "task_status": "skipped",
                "skip_reason": "candidate_deduplicated_before_evaluation",
            }

        matched = [
            dict(item)
            for item in extracted_items
            if str(item.get("candidate_id")) == candidate_id
        ]
        if not matched:
            raise RuntimeError(f"candidate not found for evaluate task: {candidate_id}")

        scoped_state = {
            **state,
            "extracted_items": matched,
            "deduped_items": list(matched),
            "evaluation_output": {},
            "scored_items": [],
            "final_decisions": [],
            "decision_reasons": [],
            "push_records": [],
            "eval_result": {},
        }
        result_state = self.run(scoped_state)
        scored_items = list(result_state.get("scored_items", []))
        decisions = list(result_state.get("final_decisions", []))
        result = next(
            (
                item
                for item in decisions
                if str(item.get("candidate_id")) == candidate_id
            ),
            None,
        )
        if result is None:
            raise RuntimeError(
                f"decision not produced for evaluate task: {candidate_id}"
            )
        scored_result = next(
            (
                item
                for item in scored_items
                if str(item.get("candidate_id")) == candidate_id
            ),
            None,
        )
        if scored_result is None:
            raise RuntimeError(
                f"score not produced for evaluate task: {candidate_id}"
            )

        state["scored_items"] = self._merge_candidate_item(
            list(state.get("scored_items", [])),
            dict(scored_result),
        )
        state["final_decisions"] = self._merge_candidate_item(
            list(state.get("final_decisions", [])),
            dict(result),
        )
        state["decision_reasons"] = [
            str(item.get("decision_reason", "")) for item in state["final_decisions"]
        ]
        state["push_records"] = [
            dict(item) for item in state["final_decisions"] if item.get("should_push")
        ]
        state["tool_results"] = list(result_state.get("tool_results", state.get("tool_results", [])))
        state["errors"] = list(result_state.get("errors", state.get("errors", [])))
        state["events"] = list(result_state.get("events", state.get("events", [])))

        eval_result = score_run(state)
        eval_result.update(_build_rag_guidance_metrics(list(state["scored_items"])))
        eval_result.update(build_eval_judge(settings=self.settings).judge(eval_result))

        evaluation_output = build_empty_evaluation_output()
        evaluation_output.update(
            {
                "deduped_items": list(state.get("deduped_items", [])),
                "scored_items": list(state["scored_items"]),
                "final_decisions": list(state["final_decisions"]),
                "decision_reasons": list(state["decision_reasons"]),
                "push_records": list(state["push_records"]),
                "eval_result": dict(eval_result),
            }
        )
        state["evaluation_output"] = evaluation_output
        state["eval_result"] = dict(eval_result)
        return dict(result)
