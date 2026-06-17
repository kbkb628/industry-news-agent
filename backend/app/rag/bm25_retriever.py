from __future__ import annotations

from dataclasses import dataclass, field
from math import log
import re
from typing import Sequence

from app.rag.knowledge_loader import KnowledgeDocument


@dataclass(frozen=True, slots=True)
class BM25RetrievedKnowledge:
    document: KnowledgeDocument
    score: float
    metadata: dict[str, object] = field(default_factory=dict)


class BM25Retriever:
    def __init__(
        self,
        documents: Sequence[KnowledgeDocument],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self._documents = list(documents)
        self.k1 = k1
        self.b = b
        self._document_tokens: dict[str, list[str]] = {
            document.doc_id: self._tokenize_document(document)
            for document in self._documents
        }
        self._document_lengths = {
            doc_id: len(tokens)
            for doc_id, tokens in self._document_tokens.items()
        }
        total_length = sum(self._document_lengths.values())
        self._average_document_length = (
            total_length / len(self._documents)
            if self._documents
            else 0.0
        )
        self._document_frequency = self._build_document_frequency()

    @staticmethod
    def _tokenize_document(document: KnowledgeDocument) -> list[str]:
        text = f"{document.title} {document.content} {' '.join(document.keywords)}"
        return re.findall(r"[a-z0-9]+", text.lower())

    def _build_document_frequency(self) -> dict[str, int]:
        frequencies: dict[str, int] = {}
        for tokens in self._document_tokens.values():
            for token in set(tokens):
                frequencies[token] = frequencies.get(token, 0) + 1
        return frequencies

    def _idf(self, token: str) -> float:
        document_count = len(self._documents)
        frequency = self._document_frequency.get(token, 0)
        return log(1 + (document_count - frequency + 0.5) / (frequency + 0.5))

    def _score_document(self, *, doc_id: str, query_tokens: set[str]) -> float:
        tokens = self._document_tokens[doc_id]
        if not tokens:
            return 0.0

        document_length = self._document_lengths[doc_id]
        average_length = self._average_document_length or 1.0
        score = 0.0
        for query_token in query_tokens:
            term_frequency = tokens.count(query_token)
            if term_frequency == 0:
                continue
            numerator = term_frequency * (self.k1 + 1)
            denominator = term_frequency + self.k1 * (
                1 - self.b + self.b * document_length / average_length
            )
            score += self._idf(query_token) * numerator / denominator
        return score

    def retrieve(self, query: str, top_k: int = 3) -> list[BM25RetrievedKnowledge]:
        query_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
        ranked: list[BM25RetrievedKnowledge] = []

        for document in self._documents:
            score = self._score_document(
                doc_id=document.doc_id,
                query_tokens=query_tokens,
            )
            if score <= 0:
                continue
            ranked.append(
                BM25RetrievedKnowledge(
                    document=document,
                    score=score,
                    metadata={"retriever": "bm25"},
                )
            )

        ranked.sort(key=lambda item: (-item.score, item.document.doc_id))
        return ranked[:top_k]
