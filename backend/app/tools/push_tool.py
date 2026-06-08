from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import DEFAULT_PUSH_THRESHOLD
from app.tools.base import FixtureTool, canonicalize_url, normalize_text


def _parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class DecidePushTool(FixtureTool):
    def __init__(self) -> None:
        super().__init__("decide_push")

    def __call__(
        self,
        *,
        run_id: str,
        topic: dict[str, Any],
        articles: list[dict[str, Any]],
        push_history: list[dict[str, Any]] | None = None,
        now: datetime | None = None,
    ) -> object:
        topic_id = str(topic["topic_id"])
        threshold = float(topic.get("push_threshold", DEFAULT_PUSH_THRESHOLD))
        cooldown_hours = int(topic.get("cooldown_hours", 24))
        decision_time = now or datetime.now(UTC)
        pushes: list[dict[str, Any]] = []
        history = push_history or []

        for article in articles:
            score = float(article.get("score", 0.0))
            canonical_url = canonicalize_url(str(article["url"]))
            normalized_title = normalize_text(str(article["title"]))

            should_push = score >= threshold
            decision_reason = (
                f"score {score:.2f} below threshold {threshold:.2f}; "
                f"{article.get('score_breakdown', '')}"
            )

            if should_push:
                duplicate_url = next(
                    (
                        record
                        for record in history
                        if canonicalize_url(str(record.get("url", ""))) == canonical_url
                    ),
                    None,
                )
                if duplicate_url is not None:
                    should_push = False
                    decision_reason = (
                        "canonical_url already exists in push_history; "
                        f"{article.get('score_breakdown', '')}"
                    )
                else:
                    cooldown_cutoff = decision_time - timedelta(hours=cooldown_hours)
                    cooldown_hit = next(
                        (
                            record
                            for record in history
                            if normalize_text(str(record.get("title", ""))) == normalized_title
                            and (_parse_timestamp(record.get("pushed_at")) or decision_time)
                            >= cooldown_cutoff
                        ),
                        None,
                    )
                    if cooldown_hit is not None:
                        should_push = False
                        decision_reason = (
                            f"title hash repeated within cooldown {cooldown_hours}h; "
                            f"{article.get('score_breakdown', '')}"
                        )
                    else:
                        decision_reason = (
                            f"score {score:.2f} meets threshold {threshold:.2f}; "
                            f"{article.get('score_breakdown', '')}"
                        )

            if should_push:
                decision_reason = (
                    f"score {score:.2f} meets threshold {threshold:.2f}; "
                    f"{article.get('score_breakdown', '')}"
                )

            pushes.append(
                {
                    "push_id": f"push_{article['candidate_id']}",
                    "run_id": run_id,
                    "topic_id": topic_id,
                    "candidate_id": article["candidate_id"],
                    "extracted_id": article.get("extracted_id"),
                    "should_push": should_push,
                    "score": score,
                    "decision_reason": decision_reason,
                    "pushed_at": None,
                }
            )

        return self.success(
            summary=f"Evaluated push decisions for {len(pushes)} article(s).",
            data={
                "pushes": pushes,
                "push_count": sum(1 for push in pushes if push["should_push"]),
                "threshold": threshold,
                "cooldown_hours": cooldown_hours,
            },
        )
