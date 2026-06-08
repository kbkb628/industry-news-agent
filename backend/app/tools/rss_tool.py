from __future__ import annotations

from typing import Any

from app.tools.base import FixtureTool


class RSSCandidatesTool(FixtureTool):
    def __init__(self) -> None:
        super().__init__("rss_fetch")

    def __call__(self, *, run_id: str, topic: dict[str, Any]) -> object:
        topic_id = str(topic["topic_id"])
        allowed_sources = {
            source["name"]
            for source in self.load_sources()
            if source.get("source_type") == "rss"
            and topic_id in source.get("topic_ids", [])
        }

        candidates = [
            {
                "candidate_id": article["candidate_id"],
                "run_id": run_id,
                "topic_id": topic_id,
                "source_type": article["source_type"],
                "source_name": article["source_name"],
                "title": article["title"],
                "url": article["url"],
                "published_at": article.get("published_at"),
                "raw_summary": article.get("raw_summary"),
                "fetch_status": "pending",
            }
            for article in self.load_articles()
            if article.get("source_type") == "rss"
            and article.get("source_name") in allowed_sources
            and topic_id in article.get("topic_ids", [])
        ]

        return self.success(
            summary=f"Loaded {len(candidates)} RSS candidate(s) from fixtures.",
            data={"run_id": run_id, "candidates": candidates},
            metadata={"source_type": "rss"},
        )
