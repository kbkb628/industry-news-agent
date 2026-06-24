from __future__ import annotations

import re
from typing import Any, Sequence

from app.rag.bm25_retriever import BM25Retriever
from app.rag.keyword_retriever import KeywordRetriever
from app.rag.knowledge_loader import KnowledgeDocument
from app.rag.local_vector_retriever import LocalVectorRetriever
from app.rag.semantic_memory import build_semantic_memory

RETRIEVAL_MODE = "hybrid_keyword_bm25_embedding_rerank"
RETRIEVERS = ("keyword", "bm25", "embedding_like")


def _metadata_query_score(document: KnowledgeDocument, query: str) -> int:
    query_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    if not query_tokens:
        return 0

    metadata = document.metadata
    metadata_values = [
        *metadata.get("topic_keywords", []),
        *metadata.get("trusted_sources", []),
        *metadata.get("source_preferences", []),
        *metadata.get("push_rules", []),
        *metadata.get("history_guidance", []),
    ]
    metadata_tokens = set(
        re.findall(r"[a-z0-9]+", " ".join(str(item) for item in metadata_values).lower())
    )
    return len(query_tokens & metadata_tokens)


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

    for document in documents:
        metadata_score = _metadata_query_score(document, query)
        if metadata_score <= 0:
            continue
        merged[document.doc_id] = {
            "document": document,
            "scores": {"keyword": float(metadata_score)},
            "retrievers": ["keyword"],
        }

    for item in keyword_hits:
        existing = merged.setdefault(
            item.document.doc_id,
            {
                "document": item.document,
                "scores": {},
                "retrievers": [],
            },
        )
        existing["scores"]["keyword"] = max(
            float(existing["scores"].get("keyword", 0.0)),
            float(item.score),
        )
        if "keyword" not in existing["retrievers"]:
            existing["retrievers"].append("keyword")

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

    documents_payload = [
        {
            "doc_id": item["document"].doc_id,
            "title": item["document"].title,
            "content": item["document"].content,
            "keywords": list(item["document"].keywords),
            "score": item["score"],
            "rerank_score": item["rerank_score"],
            "retrievers": list(item["retrievers"]),
            "scores": dict(item["scores"]),
            "metadata": dict(item["document"].metadata),
        }
        for item in ranked_hits
    ]

    return {
        "query": query,
        "retrieval_mode": RETRIEVAL_MODE,
        "retrievers": list(RETRIEVERS),
        "documents": documents_payload,
        "semantic_memory": build_semantic_memory(documents_payload),
    }
