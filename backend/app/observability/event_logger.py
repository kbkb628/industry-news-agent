from __future__ import annotations

from typing import Any

from app.observability.trace_models import EventTrace


def append_event(
    state: dict[str, Any],
    node: str,
    message: str,
    *,
    event_type: str = "node_completed",
    payload: dict[str, Any] | None = None,
    elapsed_ms: int | None = None,
) -> dict[str, Any]:
    events = list(state.get("events", []))
    events.append(
        EventTrace(
            run_id=str(state.get("run_id", "")),
            topic_id=str(state.get("topic_id", "")),
            event_type=event_type,
            node=node,
            message=message,
            payload=payload or {},
            elapsed_ms=elapsed_ms,
        ).as_dict()
    )
    state["events"] = events
    return state
