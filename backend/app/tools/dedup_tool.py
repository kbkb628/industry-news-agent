from __future__ import annotations

from typing import Any

from app.tools.base import (
    FixtureTool,
    canonicalize_url,
    content_fingerprint,
    normalize_text,
)


class DedupCandidatesTool(FixtureTool):
    def __init__(self) -> None:
        super().__init__("deduplicate_items")

    def __call__(self, *, articles: list[dict[str, Any]]) -> object:
        seen_keys: set[tuple[str, str, str]] = set()
        kept_articles: list[dict[str, Any]] = []
        dropped_candidate_ids: list[str] = []

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
                dropped_candidate_ids.append(str(article["candidate_id"]))
                continue

            seen_keys.add(dedup_key)
            kept_article = dict(article)
            kept_article["canonical_url"] = canonical_url
            kept_article["normalized_title"] = normalized_title
            kept_article["content_fingerprint"] = fingerprint
            kept_articles.append(kept_article)

        return self.success(
            summary=f"Deduplicated {len(articles)} article(s) down to {len(kept_articles)}.",
            data={
                "articles": kept_articles,
                "deduped_count": len(kept_articles),
                "dropped_candidate_ids": dropped_candidate_ids,
            },
        )
