from __future__ import annotations

from typing import Any

DEFAULT_SOURCE_PLAN = ("rss_fetch", "mock_search")


def build_source_plan(topic: dict[str, Any]) -> list[str]:
    _ = topic
    return list(DEFAULT_SOURCE_PLAN)
