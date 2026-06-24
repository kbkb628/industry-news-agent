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

    def run_fetch_task(
        self,
        task: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        candidate_id = str(task["candidate_id"])
        candidate_pool = list(state.get("retrieval_output", {}).get("candidate_pool", []))
        matched = [
            dict(candidate)
            for candidate in candidate_pool
            if str(candidate.get("candidate_id")) == candidate_id
        ]
        if not matched:
            raise RuntimeError(f"candidate not found for fetch task: {candidate_id}")

        scoped_state = {
            **state,
            "candidate_items": matched,
            "retrieval_output": {
                **dict(state.get("retrieval_output", {})),
                "candidate_pool": matched,
            },
            "fetched_contents": list(state.get("fetched_contents", [])),
            "extraction_output": dict(state.get("extraction_output", {})),
        }
        self.fetch_contents(scoped_state)
        fetched_items = list(scoped_state.get("fetched_contents", []))
        result = next(
            item for item in fetched_items if str(item.get("candidate_id")) == candidate_id
        )

        state["fetched_contents"] = self._merge_candidate_item(
            list(state.get("fetched_contents", [])),
            dict(result),
        )
        extraction_output = dict(state.get("extraction_output", {}))
        extraction_output["fetched_contents"] = list(state["fetched_contents"])
        extraction_output["content_fallbacks"] = list(
            scoped_state.get("extraction_output", {}).get("content_fallbacks", [])
        )
        state["extraction_output"] = extraction_output
        state["tool_results"] = list(scoped_state.get("tool_results", state.get("tool_results", [])))
        state["errors"] = list(scoped_state.get("errors", state.get("errors", [])))
        state["events"] = list(scoped_state.get("events", state.get("events", [])))
        return dict(result)

    def run_extract_task(
        self,
        task: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        candidate_id = str(task["candidate_id"])
        fetched_contents = list(state.get("fetched_contents", []))
        matched = [
            dict(candidate)
            for candidate in fetched_contents
            if str(candidate.get("candidate_id")) == candidate_id
        ]
        if not matched:
            raise RuntimeError(f"candidate not found for extract task: {candidate_id}")

        scoped_state = {
            **state,
            "fetched_contents": matched,
            "extracted_items": list(state.get("extracted_items", [])),
            "extraction_output": {
                **dict(state.get("extraction_output", {})),
                "fetched_contents": matched,
            },
        }
        self.extract_evidence(scoped_state)
        extracted_items = list(scoped_state.get("extracted_items", []))
        result = next(
            item for item in extracted_items if str(item.get("candidate_id")) == candidate_id
        )

        state["extracted_items"] = self._merge_candidate_item(
            list(state.get("extracted_items", [])),
            dict(result),
        )
        extraction_output = dict(state.get("extraction_output", {}))
        extraction_output["fetched_contents"] = list(state.get("fetched_contents", []))
        extraction_output["evidence_items"] = list(state["extracted_items"])
        extraction_output["extraction_failures"] = list(
            scoped_state.get("extraction_output", {}).get("extraction_failures", [])
        )
        extraction_output["content_fallbacks"] = list(
            scoped_state.get("extraction_output", {}).get("content_fallbacks", [])
        )
        state["extraction_output"] = extraction_output
        state["tool_results"] = list(scoped_state.get("tool_results", state.get("tool_results", [])))
        state["errors"] = list(scoped_state.get("errors", state.get("errors", [])))
        state["events"] = list(scoped_state.get("events", state.get("events", [])))
        return dict(result)
