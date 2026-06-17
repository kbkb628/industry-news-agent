from __future__ import annotations

from typing import Any

from app.tools.base import (
    FixtureTool,
    canonicalize_url,
    content_fingerprint,
    normalize_text,
)


class DedupCandidatesTool(FixtureTool):
    def __init__(self, *, semantic_strategy: Any | None = None) -> None:
        super().__init__("deduplicate_items")
        self.semantic_strategy = semantic_strategy

    def __call__(self, *, articles: list[dict[str, Any]]) -> object:
        seen_keys: set[tuple[str, str, str]] = set()
        kept_articles: list[dict[str, Any]] = []
        dropped_candidate_ids: list[str] = []
        drop_reasons: dict[str, dict[str, Any]] = {}

        for article in articles:
            canonical_url = canonicalize_url(str(article["url"]))
            normalized_title = normalize_text(str(article["title"]))
            fingerprint = str(
                article.get("content_fingerprint")
                or content_fingerprint(
                    content=str(article.get("content") or ""),
                    raw_summary=article.get("raw_summary"),
                )
            )
            dedup_key = (canonical_url, normalized_title, fingerprint)

            if dedup_key in seen_keys:
                candidate_id = str(article["candidate_id"])
                dropped_candidate_ids.append(candidate_id)
                drop_reasons[candidate_id] = {
                    "reason": "exact_duplicate",
                    "matched_key": (
                        "canonical_url_normalized_title_content_fingerprint"
                    ),
                }
                continue

            seen_keys.add(dedup_key)
            kept_article = dict(article)
            kept_article["canonical_url"] = canonical_url
            kept_article["normalized_title"] = normalized_title
            kept_article["content_fingerprint"] = fingerprint
            kept_articles.append(kept_article)

        semantic_dropped_candidate_ids: list[str] = []
        semantic_drop_reasons: dict[str, dict[str, Any]] = {}
        if self.semantic_strategy is not None:
            semantic_result = self.semantic_strategy.deduplicate(kept_articles)
            kept_articles = semantic_result.kept_articles
            semantic_dropped_candidate_ids = semantic_result.dropped_candidate_ids
            semantic_drop_reasons = semantic_result.drop_reasons
            dropped_candidate_ids.extend(semantic_dropped_candidate_ids)
            drop_reasons.update(semantic_drop_reasons)

        return self.success(
            summary=f"Deduplicated {len(articles)} article(s) down to {len(kept_articles)}.",
            data={
                "articles": kept_articles,
                "deduped_count": len(kept_articles),
                "dropped_candidate_ids": dropped_candidate_ids,
                "drop_reasons": drop_reasons,
                "semantic_dropped_candidate_ids": semantic_dropped_candidate_ids,
                "semantic_drop_reasons": semantic_drop_reasons,
            },
            metadata={
                "semantic_dedup_provider": (
                    None
                    if self.semantic_strategy is None
                    else self.semantic_strategy.provider
                )
            },
        )
