from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
import re
from typing import Sequence

from app.rag.knowledge_loader import KnowledgeDocument


@dataclass(frozen=True, slots=True)
class LocalVectorRetrievedKnowledge:
    document: KnowledgeDocument
    score: float
    metadata: dict[str, object] = field(default_factory=dict)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _term_vector(tokens: Sequence[str]) -> dict[str, float]:
    vector: dict[str, float] = {}
    for token in tokens:
        vector[token] = vector.get(token, 0.0) + 1.0
    return vector


def _cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    shared_tokens = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in shared_tokens)
    left_norm = sqrt(sum(value * value for value in left.values()))
    right_norm = sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


class LocalVectorRetriever:
    def __init__(self, documents: Sequence[KnowledgeDocument]) -> None:
        self._documents = list(documents)
        self._document_vectors: dict[str, dict[str, float]] = {
            document.doc_id: _term_vector(
                _tokenize(
                    f"{document.title} {document.content} {' '.join(document.keywords)}"
                )
            )
            for document in self._documents
        }

    def retrieve(self, query: str, top_k: int = 3) -> list[LocalVectorRetrievedKnowledge]:
        query_vector = _term_vector(_tokenize(query))
        ranked: list[LocalVectorRetrievedKnowledge] = []

        for document in self._documents:
            score = _cosine_similarity(
                query_vector,
                self._document_vectors[document.doc_id],
            )
            if score <= 0:
                continue
            ranked.append(
                LocalVectorRetrievedKnowledge(
                    document=document,
                    score=score,
                    metadata={"retriever": "embedding_like"},
                )
            )

        ranked.sort(key=lambda item: (-item.score, item.document.doc_id))
        return ranked[:top_k]
