from __future__ import annotations

from collections.abc import Callable
from typing import Any
import uuid

from app.tools.base import FixtureTool
from app.tools.responses import ToolResponse

try:
    import httpx
except ImportError:  # pragma: no cover - fallback only matters outside tests.
    httpx = None


class SearchCandidatesTool(FixtureTool):
    def __init__(self) -> None:
        super().__init__("mock_search")

    def __call__(self, *, run_id: str, topic: dict[str, Any]) -> object:
        topic_id = str(topic["topic_id"])
        allowed_sources = {
            source["name"]
            for source in self.load_sources()
            if source.get("source_type") == "search"
            and topic_id in source.get("topic_ids", [])
        }
        query_terms = [str(topic.get("name", "")), *topic.get("seed_keywords", [])]

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
            if article.get("source_type") == "search"
            and article.get("source_name") in allowed_sources
            and topic_id in article.get("topic_ids", [])
        ]

        return self.success(
            summary=f"Loaded {len(candidates)} search candidate(s) from fixtures.",
            data={"run_id": run_id, "candidates": candidates},
            metadata={
                "provider": "mock_search",
                "query_terms": query_terms,
                "used_fallback": False,
            },
        )


class OpenWebSearchCandidatesTool:
    def __init__(
        self,
        *,
        base_url: str,
        http_client: Any | None = None,
        timeout_seconds: float = 10.0,
        max_results: int = 10,
    ) -> None:
        self.tool_name = "search_news"
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results

    def _get_http_client(self) -> Any:
        if self.http_client is not None:
            return self.http_client
        if httpx is None:
            raise RuntimeError("httpx is unavailable for OpenWebSearch requests.")
        return httpx

    @staticmethod
    def _candidate_from_result(
        *,
        run_id: str,
        topic_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        url = str(result.get("url") or result.get("link") or "").strip()
        title = str(result.get("title") or url).strip()
        raw_summary = str(
            result.get("content")
            or result.get("snippet")
            or result.get("description")
            or ""
        ).strip()
        source_name = str(result.get("source") or "OpenWebSearch")
        candidate_key = f"{url}|{title}"

        return {
            "candidate_id": f"cand_search_{uuid.uuid5(uuid.NAMESPACE_URL, candidate_key).hex[:12]}",
            "run_id": run_id,
            "topic_id": topic_id,
            "source_type": "search",
            "source_name": source_name,
            "title": title,
            "url": url,
            "published_at": result.get("publishedDate") or result.get("published_at"),
            "raw_summary": raw_summary,
            "fetch_status": "pending",
        }

    def __call__(self, *, run_id: str, topic: dict[str, Any]) -> ToolResponse:
        topic_id = str(topic["topic_id"])
        query_terms = [str(topic.get("name", "")), *topic.get("seed_keywords", [])]
        query = " ".join(term for term in query_terms if term).strip()
        response = self._get_http_client().get(
            f"{self.base_url}/search",
            params={
                "q": query,
                "format": "json",
                "count": self.max_results,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        raw_results = payload.get("results", []) if isinstance(payload, dict) else []
        candidates = [
            self._candidate_from_result(
                run_id=run_id,
                topic_id=topic_id,
                result=dict(result),
            )
            for result in raw_results
            if isinstance(result, dict)
            and str(result.get("url") or result.get("link") or "").strip()
        ]

        return ToolResponse.success(
            tool_name=self.tool_name,
            summary=f"Loaded {len(candidates)} search candidate(s) from OpenWebSearch.",
            data={"run_id": run_id, "candidates": candidates},
            metadata={
                "provider": "open_websearch",
                "query": query,
                "query_terms": query_terms,
                "used_fallback": False,
            },
        )


class SearchProviderFallbackTool:
    def __init__(
        self,
        *,
        primary: Callable[..., ToolResponse],
        fallback: Callable[..., ToolResponse],
        provider_name: str,
        fallback_provider_name: str = "mock_search",
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.provider_name = provider_name
        self.fallback_provider_name = fallback_provider_name

    def __call__(self, **kwargs: Any) -> ToolResponse:
        try:
            return self.primary(**kwargs)
        except Exception as exc:
            fallback_response = self.fallback(**kwargs)
            return ToolResponse(
                success=fallback_response.success,
                tool_name="search_news",
                summary=(
                    f"{self.provider_name} failed; used "
                    f"{self.fallback_provider_name} fallback."
                ),
                data=fallback_response.data,
                error=fallback_response.error,
                metadata={
                    **dict(fallback_response.metadata),
                    "provider": self.provider_name,
                    "fallback_provider": self.fallback_provider_name,
                    "used_fallback": True,
                    "fallback_reason": str(exc),
                },
            )
