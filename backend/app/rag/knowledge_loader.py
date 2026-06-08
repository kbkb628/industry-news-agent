from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_KNOWLEDGE_BASE_PATH = Path(__file__).with_name("knowledge_base.jsonl")


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    doc_id: str
    title: str
    content: str
    keywords: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


def load_knowledge_base(path: Path | str = DEFAULT_KNOWLEDGE_BASE_PATH) -> list[KnowledgeDocument]:
    knowledge_path = Path(path)
    documents: list[KnowledgeDocument] = []

    with knowledge_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue

            try:
                item = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Failed to parse knowledge base line {line_number} "
                    f"in {knowledge_path}: {exc.msg}"
                ) from exc

            documents.append(
                KnowledgeDocument(
                    doc_id=item["doc_id"],
                    title=item["title"],
                    content=item["content"],
                    keywords=list(item.get("keywords", [])),
                    metadata=dict(item.get("metadata", {})),
                )
            )

    return documents
