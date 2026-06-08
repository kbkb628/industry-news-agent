from __future__ import annotations

import re
from collections.abc import Iterable

from app.llm.base import ArticleExtractionResult, BaseLLMClient, CandidateScoreResult
from app.llm.prompt_templates import (
    build_article_extraction_prompt,
    build_candidate_scoring_prompt,
    build_keyword_expansion_prompt,
)

_STOPWORDS = {
    "a",
    "an",
    "and",
    "the",
    "to",
    "for",
    "of",
    "in",
    "on",
    "with",
    "new",
}


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


class MockLLM(BaseLLMClient):
    """Deterministic local mock for tests and offline development."""

    def expand_keywords(
        self,
        topic_name: str,
        seed_keywords: Iterable[str],
    ) -> list[str]:
        seed_keyword_list = list(seed_keywords)
        build_keyword_expansion_prompt(topic_name, seed_keyword_list)
        topic_tokens = _tokenize(topic_name)
        return _dedupe_keep_order(
            [
                *seed_keyword_list,
                topic_name,
                *topic_tokens,
                "industry news",
            ]
        )

    def extract_article(
        self,
        title: str,
        content: str,
    ) -> ArticleExtractionResult:
        build_article_extraction_prompt(title, content)
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", content.strip())
            if sentence.strip()
        ]
        summary = " ".join(sentences[:2]) if sentences else content.strip()
        keywords = [
            token
            for token in _tokenize(f"{title} {content}")
            if token not in _STOPWORDS
        ]
        return ArticleExtractionResult(
            title=title.strip(),
            summary=summary[:240],
            keywords=_dedupe_keep_order(keywords)[:8],
        )

    def score_candidate(
        self,
        topic_name: str,
        candidate_title: str,
        candidate_summary: str,
    ) -> CandidateScoreResult:
        build_candidate_scoring_prompt(
            topic_name,
            candidate_title,
            candidate_summary,
        )
        topic_tokens = set(_tokenize(topic_name))
        candidate_tokens = set(_tokenize(f"{candidate_title} {candidate_summary}"))
        overlap = len(topic_tokens & candidate_tokens)

        if topic_tokens:
            score = 0.4 + 0.6 * (overlap / len(topic_tokens))
        else:
            score = 0.0

        return CandidateScoreResult(
            score=round(min(score, 1.0), 2),
            rationale=(
                f"Matched {overlap} topic keyword(s) across title and summary."
            ),
        )
