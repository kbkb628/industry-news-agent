from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.rag.knowledge_loader import KnowledgeDocument

SEMANTIC_MEMORY_KEYS = (
    "topic_keywords",
    "trusted_source_hints",
    "source_preferences",
    "push_rules",
    "history_guidance",
    "evidence_summary",
)

METADATA_MEMORY_KEYS = (
    "topic_keywords",
    "trusted_source_hints",
    "source_preferences",
    "push_rules",
    "history_guidance",
)


@dataclass(frozen=True, slots=True)
class SemanticMemorySource:
    title: str
    metadata: dict[str, object]

    @classmethod
    def from_document(cls, document: KnowledgeDocument) -> "SemanticMemorySource":
        return cls(title=document.title, metadata=dict(document.metadata))


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
    return {key: [] for key in SEMANTIC_MEMORY_KEYS}


def _coerce_sources(
    documents: Iterable[KnowledgeDocument | SemanticMemorySource],
) -> list[SemanticMemorySource]:
    sources: list[SemanticMemorySource] = []
    for document in documents:
        if isinstance(document, SemanticMemorySource):
            sources.append(document)
            continue
        sources.append(SemanticMemorySource.from_document(document))
    return sources


def build_semantic_memory(
    documents: Iterable[KnowledgeDocument | SemanticMemorySource],
) -> dict[str, list[str]]:
    sources = _coerce_sources(documents)
    if not sources:
        return build_empty_semantic_memory()

    semantic_memory = build_empty_semantic_memory()

    for document in sources:
        metadata = document.metadata
        for key in METADATA_MEMORY_KEYS:
            semantic_memory[key].extend(str(item) for item in metadata.get(key, []))

        title = document.title.strip()
        if title:
            semantic_memory["evidence_summary"].append(
                f"knowledge base matched {title}"
            )

    return {key: _dedupe(values) for key, values in semantic_memory.items()}
