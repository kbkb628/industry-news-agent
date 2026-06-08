from __future__ import annotations

from typing import Any

from app.llm.base import BaseLLMClient
from app.tools.base import FixtureTool, normalize_text


class ScoreCandidatesTool(FixtureTool):
    def __init__(self, *, llm: BaseLLMClient) -> None:
        super().__init__("score_candidate")
        self.llm = llm

    def __call__(self, *, topic: dict[str, Any], articles: list[dict[str, Any]]) -> object:
        topic_name = str(topic["name"])
        seed_keywords = [str(keyword).lower() for keyword in topic.get("seed_keywords", [])]
        trusted_sources = {
            str(source).lower() for source in topic.get("trusted_sources", [])
        }
        exclude_keywords = {
            str(keyword).lower() for keyword in topic.get("exclude_keywords", [])
        }

        scored_articles: list[dict[str, Any]] = []
        for article in articles:
            llm_score = self.llm.score_candidate(
                topic_name=topic_name,
                candidate_title=str(article["title"]),
                candidate_summary=str(article["summary"]),
            )
            search_text = normalize_text(
                " ".join(
                    [
                        str(article["title"]),
                        str(article["summary"]),
                        " ".join(str(keyword) for keyword in article.get("keywords", [])),
                    ]
                )
            )

            score = llm_score.score
            breakdown_parts = [f"base llm={llm_score.score:.2f}"]

            seed_hits = [
                keyword for keyword in seed_keywords if normalize_text(keyword) in search_text
            ]
            if seed_hits:
                bonus = min(0.15, 0.05 * len(seed_hits))
                score += bonus
                breakdown_parts.append(
                    f"seed keyword overlap +{bonus:.2f} ({', '.join(seed_hits)})"
                )

            source_name = str(article["source_name"]).lower()
            if source_name in trusted_sources:
                score += 0.10
                breakdown_parts.append("trusted source +0.10")

            exclude_hits = [
                keyword
                for keyword in exclude_keywords
                if normalize_text(keyword) in search_text
            ]
            if exclude_hits:
                penalty = 0.50
                score -= penalty
                breakdown_parts.append(
                    f"exclude keyword -{penalty:.2f} ({', '.join(exclude_hits)})"
                )

            score = max(0.0, min(round(score, 2), 1.0))

            scored_article = dict(article)
            scored_article["score"] = score
            scored_article["score_rationale"] = llm_score.rationale
            scored_article["score_breakdown"] = "; ".join(breakdown_parts)
            scored_articles.append(scored_article)

        return self.success(
            summary=f"Scored {len(scored_articles)} deduplicated article(s).",
            data={"articles": scored_articles},
        )
