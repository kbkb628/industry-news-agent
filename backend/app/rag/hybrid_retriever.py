from __future__ import annotations

from typing import Any, Sequence

from app.rag.bm25_retriever import BM25Retriever
from app.rag.keyword_retriever import KeywordRetriever
from app.rag.knowledge_loader import KnowledgeDocument
from app.rag.local_vector_retriever import LocalVectorRetriever

RETRIEVAL_MODE = "hybrid_keyword_bm25_embedding_rerank"
RETRIEVERS = ("keyword", "bm25", "embedding_like")


def retrieve_hybrid_context(
    documents: Sequence[KnowledgeDocument],
    query: str,
    *,
    top_k: int = 3,
) -> dict[str, Any]:
    keyword_hits = KeywordRetriever(documents).retrieve(query, top_k=top_k)
    bm25_hits = BM25Retriever(documents).retrieve(query, top_k=top_k)
    vector_hits = LocalVectorRetriever(documents).retrieve(query, top_k=top_k)
    merged: dict[str, dict[str, Any]] = {}

    for item in keyword_hits:
        merged[item.document.doc_id] = {
            "document": item.document,
            "scores": {"keyword": float(item.score)},
            "retrievers": ["keyword"],
        }

    for retriever_name, hits in (
        ("bm25", bm25_hits),
        ("embedding_like", vector_hits),
    ):
        for item in hits:
            existing = merged.setdefault(
                item.document.doc_id,
                {
                    "document": item.document,
                    "scores": {},
                    "retrievers": [],
                },
            )
            existing["scores"][retriever_name] = float(item.score)
            if retriever_name not in existing["retrievers"]:
                existing["retrievers"].append(retriever_name)

    for item in merged.values():
        scores = dict(item["scores"])
        item["score"] = (
            scores.get("keyword", 0.0)
            + scores.get("bm25", 0.0)
            + scores.get("embedding_like", 0.0)
        )
        item["rerank_score"] = (
            scores.get("keyword", 0.0) * 0.30
            + scores.get("bm25", 0.0) * 0.35
            + scores.get("embedding_like", 0.0) * 0.35
        )

    ranked_hits = sorted(
        merged.values(),
        key=lambda item: (-float(item["rerank_score"]), item["document"].doc_id),
    )[:top_k]

    return {
        "query": query,
        "retrieval_mode": RETRIEVAL_MODE,
        "retrievers": list(RETRIEVERS),
        "documents": [
            {
                "doc_id": item["document"].doc_id,
                "title": item["document"].title,
                "content": item["document"].content,
                "keywords": list(item["document"].keywords),
                "score": item["score"],
                "rerank_score": item["rerank_score"],
                "retrievers": list(item["retrievers"]),
                "scores": dict(item["scores"]),
            }
            for item in ranked_hits
        ],
    }
