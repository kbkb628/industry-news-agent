from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        lowered = normalized.lower()
        if not normalized or lowered in seen:
            continue
        seen.add(lowered)
        result.append(normalized)
    return result


def build_empty_semantic_memory() -> dict[str, list[str]]:
    return {
        "topic_keywords": [],
        "trusted_source_hints": [],
        "source_preferences": [],
        "push_rules": [],
        "history_guidance": [],
        "evidence_summary": [],
    }


def build_semantic_memory(documents: list[dict[str, Any]]) -> dict[str, list[str]]:
    if not documents:
        return build_empty_semantic_memory()

    topic_keywords: list[str] = []
    trusted_source_hints: list[str] = []
    source_preferences: list[str] = []
    push_rules: list[str] = []
    history_guidance: list[str] = []
    evidence_summary: list[str] = []

    for document in documents:
        metadata = dict(document.get("metadata", {}))
        topic_keywords.extend(str(item) for item in metadata.get("topic_keywords", []))
        trusted_source_hints.extend(
            str(item) for item in metadata.get("trusted_sources", [])
        )
        source_preferences.extend(
            str(item) for item in metadata.get("source_preferences", [])
        )
        push_rules.extend(str(item) for item in metadata.get("push_rules", []))
        history_guidance.extend(
            str(item) for item in metadata.get("history_guidance", [])
        )

        title = str(document.get("title", "")).strip()
        if title:
            evidence_summary.append(f"knowledge base matched {title.lower()}")

    return {
        "topic_keywords": _dedupe(topic_keywords),
        "trusted_source_hints": _dedupe(trusted_source_hints),
        "source_preferences": _dedupe(source_preferences),
        "push_rules": _dedupe(push_rules),
        "history_guidance": _dedupe(history_guidance),
        "evidence_summary": _dedupe(evidence_summary),
    }
