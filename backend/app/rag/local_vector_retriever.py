from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
import hashlib
import re
from typing import Sequence

from app.rag.knowledge_loader import KnowledgeDocument


@dataclass(frozen=True, slots=True)
class LocalVectorRetrievedKnowledge:
    document: KnowledgeDocument
    score: float
    metadata: dict[str, object] = field(default_factory=dict)


_CANONICAL_ALIASES: dict[str, tuple[str, ...]] = {
    "mcp": ("model context protocol",),
    "rag": ("retrieval augmented generation",),
    "llm": ("large language model",),
    "api": ("application programming interface",),
}


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _canonicalize_text(text: str) -> str:
    canonical = text.lower()
    for short_form, aliases in _CANONICAL_ALIASES.items():
        for alias in aliases:
            canonical = canonical.replace(alias, short_form)
    return canonical


def _canonical_tokens(text: str) -> set[str]:
    return set(_tokenize(_canonicalize_text(text)))


def _char_ngrams(text: str, *, minimum: int, maximum: int) -> list[str]:
    normalized = re.sub(r"[^a-z0-9]+", "", _canonicalize_text(text))
    if not normalized:
        return []

    grams: list[str] = []
    for size in range(minimum, maximum + 1):
        if len(normalized) < size:
            continue
        for index in range(len(normalized) - size + 1):
            grams.append(normalized[index : index + size])
    return grams


def _hashed_embedding(
    text: str,
    *,
    dimensions: int,
    char_ngram_min: int,
    char_ngram_max: int,
) -> list[float]:
    vector = [0.0] * dimensions
    grams = _char_ngrams(
        text,
        minimum=char_ngram_min,
        maximum=char_ngram_max,
    )
    if not grams:
        return vector

    for gram in grams:
        digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        magnitude = 1.0 + (digest[5] / 255.0)
        vector[bucket] += sign * magnitude

    norm = sqrt(sum(component * component for component in vector))
    if norm == 0:
        return vector
    return [component / norm for component in vector]


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(left_value * right_value for left_value, right_value in zip(left, right))
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


class LocalVectorRetriever:
    def __init__(
        self,
        documents: Sequence[KnowledgeDocument],
        *,
        dimensions: int = 256,
        char_ngram_min: int = 3,
        char_ngram_max: int = 5,
        min_score: float = 0.18,
    ) -> None:
        self._documents = list(documents)
        self.dimensions = dimensions
        self.char_ngram_min = char_ngram_min
        self.char_ngram_max = char_ngram_max
        self.min_score = min_score
        self._document_vectors: dict[str, list[float]] = {
            document.doc_id: _hashed_embedding(
                f"{document.title} {document.content} {' '.join(document.keywords)}",
                dimensions=self.dimensions,
                char_ngram_min=self.char_ngram_min,
                char_ngram_max=self.char_ngram_max,
            )
            for document in self._documents
        }
        self._document_tokens: dict[str, set[str]] = {
            document.doc_id: _canonical_tokens(
                f"{document.title} {document.content} {' '.join(document.keywords)}"
            )
            for document in self._documents
        }

    def retrieve(self, query: str, top_k: int = 3) -> list[LocalVectorRetrievedKnowledge]:
        query_vector = _hashed_embedding(
            query,
            dimensions=self.dimensions,
            char_ngram_min=self.char_ngram_min,
            char_ngram_max=self.char_ngram_max,
        )
        query_tokens = _canonical_tokens(query)
        ranked: list[LocalVectorRetrievedKnowledge] = []

        for document in self._documents:
            embedding_score = _cosine_similarity(
                query_vector,
                self._document_vectors[document.doc_id],
            )
            overlap_score = 0.0
            if query_tokens:
                shared_tokens = query_tokens & self._document_tokens[document.doc_id]
                overlap_score = len(shared_tokens) / len(query_tokens)
            score = embedding_score * 0.6 + overlap_score * 0.4
            if score < self.min_score:
                continue
            ranked.append(
                LocalVectorRetrievedKnowledge(
                    document=document,
                    score=score,
                    metadata={
                        "retriever": "embedding",
                        "embedding_provider": "local",
                        "embedding_backend": "hashed",
                        "embedding_model": "local_hashed_char_ngram",
                        "dimensions": self.dimensions,
                        "char_ngram_min": self.char_ngram_min,
                        "char_ngram_max": self.char_ngram_max,
                        "min_score": self.min_score,
                        "embedding_score": embedding_score,
                        "overlap_score": overlap_score,
                        "used_fallback": False,
                        "fallback_reason": None,
                    },
                )
            )

        ranked.sort(key=lambda item: (-item.score, item.document.doc_id))
        return ranked[:top_k]
