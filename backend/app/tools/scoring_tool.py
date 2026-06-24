from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.llm.base import BaseLLMClient
from app.tools.base import FixtureTool, normalize_text


def _normalized_domain(value: object) -> str:
    text = str(value).strip().lower()
    if not text:
        return ""
    host = urlparse(text).netloc if "://" in text else text
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


class ScoreCandidatesTool(FixtureTool):
    def __init__(self, *, llm: BaseLLMClient) -> None:
        super().__init__("score_candidate")
        self.llm = llm

    def __call__(
        self,
        *,
        topic: dict[str, Any],
        articles: list[dict[str, Any]],
        business_context: dict[str, Any] | None = None,
    ) -> object:
        topic_name = str(topic["name"])
        seed_keywords = [str(keyword).lower() for keyword in topic.get("seed_keywords", [])]
        trusted_sources = {
            _normalized_domain(source) for source in topic.get("trusted_sources", [])
        }
        semantic_memory = dict((business_context or {}).get("semantic_memory", {}) or {})
        semantic_trusted_sources = {
            _normalized_domain(source)
            for source in semantic_memory.get("trusted_source_hints", [])
        }
        push_rules = [
            str(rule).strip()
            for rule in semantic_memory.get("push_rules", [])
            if str(rule).strip()
        ]
        history_guidance = [
            str(rule).strip()
            for rule in semantic_memory.get("history_guidance", [])
            if str(rule).strip()
        ]
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
            rag_guidance_hits: list[str] = []

            seed_hits = [
                keyword for keyword in seed_keywords if normalize_text(keyword) in search_text
            ]
            if seed_hits:
                bonus = min(0.15, 0.05 * len(seed_hits))
                score += bonus
                breakdown_parts.append(
                    f"seed keyword overlap +{bonus:.2f} ({', '.join(seed_hits)})"
                )

            source_name = _normalized_domain(article.get("source_name", ""))
            url_host = _normalized_domain(article.get("url", ""))
            trusted_match_targets = {target for target in (source_name, url_host) if target}
            if trusted_match_targets & trusted_sources:
                score += 0.10
                breakdown_parts.append("trusted source +0.10")
            semantic_trusted_source_match = bool(
                trusted_match_targets & semantic_trusted_sources
            )
            if semantic_trusted_source_match:
                score += 0.10
                breakdown_parts.append("semantic trusted source +0.10")

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

            if push_rules:
                rag_guidance_hits.append("push_rules")
            if history_guidance:
                rag_guidance_hits.append("history_guidance")
            if rag_guidance_hits:
                breakdown_parts.append(f"guidance: {', '.join(rag_guidance_hits)}")

            score = max(0.0, min(round(score, 2), 1.0))

            scored_article = dict(article)
            scored_article["score"] = score
            scored_article["score_rationale"] = llm_score.rationale
            scored_article["score_breakdown"] = "; ".join(breakdown_parts)
            scored_article["rag_guidance_hits"] = rag_guidance_hits
            scored_article["trusted_source_match"] = semantic_trusted_source_match
            scored_articles.append(scored_article)

        return self.success(
            summary=f"Scored {len(scored_articles)} deduplicated article(s).",
            data={"articles": scored_articles},
        )
