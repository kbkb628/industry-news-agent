from __future__ import annotations

from typing import Any

from app.llm.base import BaseLLMClient
from app.tools.base import FixtureTool, content_fingerprint


class ExtractCandidatesTool(FixtureTool):
    def __init__(self, *, llm: BaseLLMClient) -> None:
        super().__init__("extract_article")
        self.llm = llm

    def __call__(
        self,
        *,
        run_id: str,
        topic: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> object:
        topic_id = str(topic["topic_id"])
        articles: list[dict[str, Any]] = []
        skipped_candidate_ids: list[str] = []

        for candidate in candidates:
            fetch_status = str(candidate.get("fetch_status", "pending"))
            content = str(candidate.get("content") or "")
            raw_summary = str(candidate.get("raw_summary") or "").strip()
            extracted_title = str(candidate["title"])

            if fetch_status == "fetched" and content:
                extraction = self.llm.extract_article(
                    title=extracted_title,
                    content=content,
                )
                extracted_title = extraction.title
                summary = extraction.summary
                keywords = extraction.keywords
                extraction_mode = "full_content"
            elif raw_summary:
                summary = raw_summary
                keywords = self.llm.extract_article(
                    title=extracted_title,
                    content=raw_summary,
                ).keywords
                extraction_mode = "raw_summary"
            else:
                skipped_candidate_ids.append(str(candidate["candidate_id"]))
                continue

            articles.append(
                {
                    "extracted_id": f"ext_{candidate['candidate_id']}",
                    "run_id": run_id,
                    "topic_id": topic_id,
                    "candidate_id": candidate["candidate_id"],
                    "source_type": candidate["source_type"],
                    "source_name": candidate["source_name"],
                    "title": extracted_title,
                    "url": candidate["url"],
                    "published_at": candidate.get("published_at"),
                    "raw_summary": candidate.get("raw_summary"),
                    "summary": summary,
                    "keywords": keywords,
                    "content": content,
                    "content_fingerprint": content_fingerprint(
                        content=content,
                        raw_summary=candidate.get("raw_summary"),
                    ),
                    "fetch_status": fetch_status,
                    "fetch_error": candidate.get("fetch_error"),
                    "extraction_mode": extraction_mode,
                }
            )

        return self.success(
            summary=f"Extracted {len(articles)} article summary item(s).",
            data={
                "articles": articles,
                "skipped_candidate_ids": skipped_candidate_ids,
            },
        )
