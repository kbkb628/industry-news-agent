from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
import uuid


def utc_now() -> datetime:
    return datetime.now(UTC)


def _generate_trace_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True, slots=True)
class EventTrace:
    run_id: str
    topic_id: str
    event_type: str
    node: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: int | None = None
    created_at: datetime = field(default_factory=utc_now)
    event_id: str = field(default_factory=lambda: _generate_trace_id("evt"))

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat().replace("+00:00", "Z")
        return payload
