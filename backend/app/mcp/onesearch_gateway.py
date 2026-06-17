from __future__ import annotations

from typing import Any
import uuid

from app.mcp.gateway import ToolCallable, ToolGateway
from app.tools.responses import ToolResponse

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None


class OneSearchMCPGateway(ToolGateway):
    def __init__(
        self,
        *,
        base_url: str,
        fallback_gateway: ToolGateway,
        http_client: Any | None = None,
        timeout_seconds: float = 10.0,
        max_results: int = 10,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.fallback_gateway = fallback_gateway
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results
        self._handlers: dict[str, ToolCallable] = {}

    def register(self, tool_name: str, handler: ToolCallable) -> None:
        self._handlers[tool_name] = handler

    def _get_http_client(self) -> Any:
        if self.http_client is not None:
            return self.http_client
        if httpx is None:
            raise RuntimeError("httpx is unavailable for OneSearch requests.")
        return httpx

    @staticmethod
    def _build_query(topic: dict[str, Any]) -> tuple[str, list[str]]:
        query_terms = [str(topic.get("name", "")), *topic.get("seed_keywords", [])]
        query = " ".join(term for term in query_terms if term).strip()
        return query, query_terms

    @staticmethod
    def _map_result(
        *,
        run_id: str,
        topic_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        url = str(result.get("url") or "").strip()
        title = str(result.get("title") or url).strip()
        snippet = str(result.get("snippet") or result.get("content") or "").strip()
        source_name = str(result.get("source") or "OneSearch")
        candidate_key = f"{url}|{title}"
        return {
            "candidate_id": f"cand_search_{uuid.uuid5(uuid.NAMESPACE_URL, candidate_key).hex[:12]}",
            "run_id": run_id,
            "topic_id": topic_id,
            "source_type": "search",
            "source_name": source_name,
            "title": title,
            "url": url,
            "published_at": result.get("published_at"),
            "raw_summary": snippet,
            "fetch_status": "pending",
        }

    def _search_news(self, *, run_id: str, topic: dict[str, Any]) -> ToolResponse:
        topic_id = str(topic["topic_id"])
        query, query_terms = self._build_query(topic)
        try:
            response = self._get_http_client().post(
                f"{self.base_url}/search",
                json={"query": query, "max_results": self.max_results},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            raw_results = payload.get("results", []) if isinstance(payload, dict) else []
            candidates = [
                self._map_result(
                    run_id=run_id,
                    topic_id=topic_id,
                    result=dict(item),
                )
                for item in raw_results
                if isinstance(item, dict) and str(item.get("url") or "").strip()
            ]
            return ToolResponse.success(
                tool_name="search_news",
                summary=f"Loaded {len(candidates)} search candidate(s) from OneSearch.",
                data={"run_id": run_id, "candidates": candidates},
                metadata={
                    "provider": "onesearch_mcp",
                    "query": query,
                    "query_terms": query_terms,
                    "used_fallback": False,
                },
            )
        except Exception as exc:
            fallback_response = self.fallback_gateway.call(
                "search_news",
                run_id=run_id,
                topic=topic,
            )
            return ToolResponse(
                success=fallback_response.success,
                tool_name="search_news",
                summary="onesearch_mcp failed; used mock_search fallback.",
                data=fallback_response.data,
                error=fallback_response.error,
                metadata={
                    **dict(fallback_response.metadata),
                    "provider": "onesearch_mcp",
                    "fallback_provider": "mock_search",
                    "used_fallback": True,
                    "fallback_reason": str(exc),
                },
            )

    def call(self, tool_name: str, **kwargs: object) -> ToolResponse:
        if tool_name == "search_news":
            return self._search_news(
                run_id=str(kwargs["run_id"]),
                topic=dict(kwargs["topic"]),
            )
        return self.fallback_gateway.call(tool_name, **kwargs)
