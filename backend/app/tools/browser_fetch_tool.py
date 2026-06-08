from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    import httpx
except ImportError:  # pragma: no cover - fallback only matters outside tests.
    httpx = None

from app.tools.base import FixtureTool, canonicalize_url


class BrowserFetchTool(FixtureTool):
    def __init__(
        self,
        *,
        fetcher: Callable[[str], str] | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        super().__init__("fetch_article_content")
        self.fetcher = fetcher
        self.timeout_seconds = timeout_seconds

    def __call__(self, *, candidates: list[dict[str, Any]]) -> object:
        article_by_candidate_id = {
            str(article["candidate_id"]): article for article in self.load_articles()
        }
        article_by_url = {
            canonicalize_url(article["url"]): article for article in self.load_articles()
        }
        fetched_candidates: list[dict[str, Any]] = []

        for candidate in candidates:
            resolved = dict(candidate)
            article = article_by_candidate_id.get(str(candidate["candidate_id"]))
            if article is None:
                article = article_by_url.get(canonicalize_url(str(candidate["url"])))

            try:
                if article is not None:
                    content = str(article.get("content", ""))
                elif self.fetcher is not None:
                    content = self.fetcher(str(candidate["url"]))
                elif httpx is not None:
                    response = httpx.get(
                        str(candidate["url"]),
                        follow_redirects=True,
                        timeout=self.timeout_seconds,
                    )
                    response.raise_for_status()
                    content = response.text
                else:
                    raise RuntimeError("httpx is unavailable for remote fetches.")

                resolved["fetch_status"] = "fetched"
                resolved["content"] = content
            except Exception as exc:
                resolved["fetch_status"] = "failed"
                resolved["content"] = ""
                resolved["fetch_error"] = str(exc)

            fetched_candidates.append(resolved)

        return self.success(
            summary=f"Fetched {len(fetched_candidates)} candidate page(s).",
            data={"candidates": fetched_candidates},
        )
