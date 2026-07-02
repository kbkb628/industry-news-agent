from __future__ import annotations

from typing import Any, Sequence

from app.rag.knowledge_loader import KnowledgeDocument
from app.rag.local_vector_retriever import (
    LocalVectorRetrievedKnowledge,
    _canonical_tokens,
    _cosine_similarity,
)


def _build_document_text(document: KnowledgeDocument) -> str:
    return f"{document.title} {document.content} {' '.join(document.keywords)}".strip()


class OpenAICompatibleEmbeddingRetriever:
    def __init__(
        self,
        documents: Sequence[KnowledgeDocument],
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 10.0,
        min_score: float = 0.18,
        http_client: Any | None = None,
    ) -> None:
        self._documents = list(documents)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.min_score = min_score
        self.http_client = http_client
        self._document_tokens: dict[str, set[str]] = {
            document.doc_id: _canonical_tokens(_build_document_text(document))
            for document in self._documents
        }

    def _get_http_client(self) -> Any:
        if self.http_client is not None:
            return self.http_client
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is unavailable for embedding requests.") from exc
        return httpx.Client()

    def _embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        client = self._get_http_client()
        response = client.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": list(texts),
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data", [])
        if not isinstance(items, list) or len(items) != len(texts):
            raise RuntimeError("embedding response length mismatch")

        embeddings: list[list[float]] = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
                raise RuntimeError("embedding response payload is malformed")
            embeddings.append([float(value) for value in item["embedding"]])
        return embeddings

    def retrieve(self, query: str, top_k: int = 3) -> list[LocalVectorRetrievedKnowledge]:
        query_tokens = _canonical_tokens(query)
        document_texts = [_build_document_text(document) for document in self._documents]
        vectors = self._embed_texts([query, *document_texts])
        query_vector = vectors[0]
        document_vectors = vectors[1:]

        ranked: list[LocalVectorRetrievedKnowledge] = []
        for document, document_vector in zip(self._documents, document_vectors):
            embedding_score = _cosine_similarity(query_vector, document_vector)
            overlap_score = 0.0
            if query_tokens:
                shared_tokens = query_tokens & self._document_tokens[document.doc_id]
                overlap_score = len(shared_tokens) / len(query_tokens)
            score = embedding_score * 0.6 + overlap_score * 0.4
            if score < self.min_score:
                continue
            ranked.append(
                LocalVectorRetrievedKnowledge(
                    document=document,
                    score=score,
                    metadata={
                        "retriever": "embedding",
                        "embedding_provider": "external",
                        "embedding_backend": "openai_compatible",
                        "embedding_model": self.model,
                        "embedding_score": embedding_score,
                        "overlap_score": overlap_score,
                        "used_fallback": False,
                        "fallback_reason": None,
                    },
                )
            )

        ranked.sort(key=lambda item: (-item.score, item.document.doc_id))
        return ranked[:top_k]
