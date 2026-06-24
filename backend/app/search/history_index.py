from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from urllib.parse import quote

try:
    import httpx
except ImportError:  # pragma: no cover - fallback only matters outside tests.
    httpx = None

from app.core.config import Settings


class HistoryIndexProtocol(Protocol):
    def index_candidates(self, candidates: list[dict[str, Any]]) -> dict[str, Any]: ...
    def search_candidates(
        self,
        query: str,
        top_k: int = 5,
        *,
        exclude_run_id: str | None = None,
        exclude_candidate_ids: list[str] | None = None,
    ) -> dict[str, Any]: ...


class NoopHistoryIndex:
    def index_candidates(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        return {"indexed_count": 0, "provider": "none"}

    def search_candidates(
        self,
        query: str,
        top_k: int = 5,
        *,
        exclude_run_id: str | None = None,
        exclude_candidate_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        _ = top_k
        _ = exclude_run_id
        _ = exclude_candidate_ids
        return {"provider": "none", "query": query, "items": []}


class OpenSearchHistoryIndex:
    def __init__(
        self,
        *,
        base_url: str,
        index_name: str,
        http_client: Any | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.index_name = index_name.strip("/")
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds

    def index_candidates(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        client = self.http_client
        if client is None:
            if httpx is None:
                raise RuntimeError("httpx is unavailable for OpenSearch indexing.")
            client = httpx

        indexed_count = 0
        for candidate in candidates:
            document = self._build_document(candidate)
            document_id = self._build_document_id(candidate)
            response = client.put(
                f"{self.base_url}/{self.index_name}/_doc/{document_id}",
                json=document,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            indexed_count += 1

        return {"indexed_count": indexed_count, "provider": "opensearch"}

    def search_candidates(
        self,
        query: str,
        top_k: int = 5,
        *,
        exclude_run_id: str | None = None,
        exclude_candidate_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        client = self.http_client
        if client is None:
            if httpx is None:
                raise RuntimeError("httpx is unavailable for OpenSearch search.")
            client = httpx

        must_not: list[dict[str, Any]] = []
        if exclude_run_id:
            must_not.append({"term": {"run_id": exclude_run_id}})
        _ = exclude_candidate_ids

        query_body: dict[str, Any] = {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": [
                                "title^3",
                                "raw_summary^2",
                                "content",
                                "decision_reason",
                            ],
                        }
                    }
                ]
            }
        }
        if must_not:
            query_body["bool"]["must_not"] = must_not

        response = client.post(
            f"{self.base_url}/{self.index_name}/_search",
            json={
                "size": top_k,
                "query": query_body,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        hits = payload.get("hits", {}).get("hits", [])
        return {
            "provider": "opensearch",
            "query": query,
            "items": [dict(hit.get("_source", {})) for hit in hits],
        }

    @staticmethod
    def _build_document_id(candidate: dict[str, Any]) -> str:
        raw_document_id = f"{candidate['run_id']}-{candidate['candidate_id']}"
        return quote(raw_document_id, safe="")

    @staticmethod
    def _build_document(candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "candidate_id": str(candidate["candidate_id"]),
            "run_id": str(candidate["run_id"]),
            "topic_id": str(candidate["topic_id"]),
            "source_type": str(candidate.get("source_type", "")),
            "source_name": str(candidate.get("source_name", "")),
            "title": str(candidate.get("title", "")),
            "url": str(candidate.get("url", "")),
            "raw_summary": candidate.get("raw_summary"),
            "content": candidate.get("content"),
            "score": candidate.get("score"),
            "decision": candidate.get("decision"),
            "decision_reason": candidate.get("decision_reason"),
            "created_at": _json_safe(candidate.get("created_at")),
        }


def build_history_index(
    *,
    settings: Settings | None = None,
    http_client: Any | None = None,
) -> HistoryIndexProtocol:
    if (
        settings is None
        or settings.history_index_provider != "opensearch"
        or not settings.opensearch_base_url
    ):
        return NoopHistoryIndex()

    return OpenSearchHistoryIndex(
        base_url=settings.opensearch_base_url,
        index_name=settings.opensearch_index_name,
        http_client=http_client,
        timeout_seconds=settings.opensearch_timeout_seconds,
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return value
