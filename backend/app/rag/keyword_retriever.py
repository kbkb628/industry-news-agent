from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from app.rag.knowledge_loader import KnowledgeDocument


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


@dataclass(frozen=True, slots=True)
class RetrievedKnowledge:
    document: KnowledgeDocument
    score: int


class KeywordRetriever:
    def __init__(self, documents: Sequence[KnowledgeDocument]) -> None:
        self._documents = list(documents)
        self._document_tokens: dict[str, set[str]] = {
            document.doc_id: _tokenize(
                f"{document.title} {document.content} {' '.join(document.keywords)}"
            )
            for document in self._documents
        }

    def retrieve(self, query: str, top_k: int = 3) -> list[RetrievedKnowledge]:
        query_tokens = _tokenize(query)
        ranked: list[RetrievedKnowledge] = []

        for document in self._documents:
            document_tokens = self._document_tokens[document.doc_id]
            score = len(query_tokens & document_tokens)
            if score <= 0:
                continue
            ranked.append(RetrievedKnowledge(document=document, score=score))

        ranked.sort(key=lambda item: (-item.score, item.document.doc_id))
        return ranked[:top_k]
