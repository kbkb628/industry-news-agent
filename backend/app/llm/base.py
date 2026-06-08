from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ArticleExtractionResult:
    title: str
    summary: str
    keywords: list[str]


@dataclass(frozen=True, slots=True)
class CandidateScoreResult:
    score: float
    rationale: str


class BaseLLMClient(ABC):
    @abstractmethod
    def expand_keywords(
        self,
        topic_name: str,
        seed_keywords: Iterable[str],
    ) -> list[str]:
        """Return a deterministic keyword expansion for the topic."""

    @abstractmethod
    def extract_article(
        self,
        title: str,
        content: str,
    ) -> ArticleExtractionResult:
        """Extract a compact article summary and stable keywords."""

    @abstractmethod
    def score_candidate(
        self,
        topic_name: str,
        candidate_title: str,
        candidate_summary: str,
    ) -> CandidateScoreResult:
        """Score a candidate article against a topic."""
