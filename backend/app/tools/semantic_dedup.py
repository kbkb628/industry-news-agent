from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class SemanticDedupResult:
    kept_articles: list[dict[str, Any]]
    dropped_candidate_ids: list[str]
    drop_reasons: dict[str, dict[str, Any]]


class LocalSemanticDedupStrategy:
    provider = "local"

    def __init__(self, *, threshold: float = 0.88) -> None:
        self.threshold = threshold

    def deduplicate(self, articles: list[dict[str, Any]]) -> SemanticDedupResult:
        kept_articles: list[dict[str, Any]] = []
        kept_vectors: list[dict[str, float]] = []
        dropped_candidate_ids: list[str] = []
        drop_reasons: dict[str, dict[str, Any]] = {}

        for article in articles:
            candidate_id = str(article["candidate_id"])
            vector = _term_vector(_article_text(article))
            match = self._find_match(vector, kept_vectors, kept_articles)
            if match is not None:
                matched_article, score = match
                dropped_candidate_ids.append(candidate_id)
                drop_reasons[candidate_id] = {
                    "reason": "semantic_similarity",
                    "matched_candidate_id": matched_article["candidate_id"],
                    "similarity": round(score, 4),
                }
                continue

            kept_articles.append(dict(article))
            kept_vectors.append(vector)

        return SemanticDedupResult(
            kept_articles=kept_articles,
            dropped_candidate_ids=dropped_candidate_ids,
            drop_reasons=drop_reasons,
        )

    def _find_match(
        self,
        vector: dict[str, float],
        kept_vectors: list[dict[str, float]],
        kept_articles: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], float] | None:
        best_match: tuple[dict[str, Any], float] | None = None
        for kept_article, kept_vector in zip(kept_articles, kept_vectors):
            score = _cosine_similarity(vector, kept_vector)
            if score >= self.threshold and (
                best_match is None or score > best_match[1]
            ):
                best_match = (kept_article, score)
        return best_match


def _article_text(article: dict[str, Any]) -> str:
    return " ".join(
        str(article.get(field) or "")
        for field in ("title", "summary", "raw_summary", "content")
    )


def _tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def _term_vector(text: str) -> dict[str, float]:
    vector: dict[str, float] = {}
    for token in _tokenize(text):
        vector[token] = vector.get(token, 0.0) + 1.0
    return vector


def _cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    shared_tokens = set(left) & set(right)
    dot_product = sum(left[token] * right[token] for token in shared_tokens)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot_product / (left_norm * right_norm)
