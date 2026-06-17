from __future__ import annotations

from typing import Any

from app.agent.contracts import build_empty_extraction_output
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


class ExtractionAgent:
    def __init__(self, *, gateway: ToolGateway) -> None:
        self.gateway = gateway

    def fetch_contents(self, state: dict[str, Any]) -> dict[str, Any]:
        retrieval_output = dict(state.get("retrieval_output", {}))
        candidate_pool = list(
            retrieval_output.get("candidate_pool", state.get("candidate_items", []))
        )
        extraction_output = dict(state.get("extraction_output", {}))
        content_fallbacks = list(extraction_output.get("content_fallbacks", []))

        fetch_response = _call_tool(
            state,
            self.gateway,
            "fetch_article_content",
            candidates=candidate_pool,
        )
        fetched_contents = list(dict(fetch_response.data or {}).get("candidates", []))

        if fetch_response.metadata.get("used_browser_fallback"):
            fallback_record = {
                "tool_name": fetch_response.tool_name,
                "fallback": "browser_fetch",
            }
            content_fallbacks.append(fallback_record)
            append_event(
                state,
                "fetch_contents",
                "Used browser fallback for one or more candidate pages.",
                event_type="fallback_used",
                payload=fallback_record,
            )

        extraction_output = {
            **build_empty_extraction_output(),
            **extraction_output,
            "fetched_contents": fetched_contents,
            "content_fallbacks": content_fallbacks,
        }
        state["extraction_output"] = extraction_output

        # Keep legacy fields populated until stage-level finalization takes over.
        state["fetched_contents"] = fetched_contents

        return state

    def extract_evidence(self, state: dict[str, Any]) -> dict[str, Any]:
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
        fetched_contents = list(
            extraction_output.get("fetched_contents", state.get("fetched_contents", []))
        )
        extraction_failures = list(extraction_output.get("extraction_failures", []))

        extract_response = _call_tool(
            state,
            self.gateway,
            "extract_article",
            run_id=run_id,
            topic=topic,
            candidates=fetched_contents,
        )
        evidence_items = list(dict(extract_response.data or {}).get("articles", []))

        raw_summary_fallbacks = [
            item for item in evidence_items if item.get("extraction_mode") == "raw_summary"
        ]
        if raw_summary_fallbacks:
            append_event(
                state,
                "extract_structured_items",
                "Used raw_summary fallback for one or more candidates.",
                event_type="fallback_used",
                payload={"fallback_count": len(raw_summary_fallbacks)},
            )

        extraction_output = {
            **build_empty_extraction_output(),
            **extraction_output,
            "fetched_contents": fetched_contents,
            "content_fallbacks": list(extraction_output.get("content_fallbacks", [])),
            "evidence_items": evidence_items,
            "extraction_failures": extraction_failures,
        }

        state["extraction_output"] = extraction_output

        # Keep legacy fields populated until stage-level finalization takes over.
        state["extracted_items"] = evidence_items

        return state

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        self.fetch_contents(state)
        self.extract_evidence(state)
        extraction_output = dict(state.get("extraction_output", {}))
        extraction_output.update(
            {
                "fetched_contents": list(state.get("fetched_contents", [])),
                "evidence_items": list(state.get("extracted_items", [])),
            }
        )

        state["extraction_output"] = extraction_output
        return state
