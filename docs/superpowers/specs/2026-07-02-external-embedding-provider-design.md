# External-First Embedding Provider For RAG Retrieval

**Goal:** Add a truthful external embedding provider path to the existing RAG retrieval layer, with Alibaba Bailian-compatible OpenAI-style embeddings as the primary runtime path and the current local hashed embedding retriever kept only as explicit fallback.

**Scope:** This design covers backend retrieval configuration, provider invocation, fallback handling, runtime metadata, tests, and documentation updates for the current in-process knowledge-base RAG path. It does not introduce a vector database, external indexing pipeline, new dashboard pages, or semantic history dedup changes.

**Why now:** The repository currently claims only a local hashed-embedding path, while the user has explicitly chosen an external-model-first direction for future vector capability and already has a Bailian-compatible API key available in the local environment. The project should therefore support a real provider-backed embedding path without overstating the deployment boundary.

---

## 1. Current State

The current RAG retrieval path is local-only:

- `retrieve_hybrid_context(...)` combines keyword, BM25, and `LocalVectorRetriever`
- `LocalVectorRetriever` builds deterministic hashed vectors in-process
- `Settings` exposes only local embedding tuning knobs
- README and resume-alignment docs explicitly scope the project to local hashed embeddings

Current limitations:

- there is no external embedding provider boundary in config or code
- the project cannot truthfully demonstrate a real model-backed embedding call
- environment variables like `TONGYI_API_KEY` are not consumed by the app
- no runtime metadata distinguishes provider-backed embedding retrieval from local fallback

This design adds the external provider path without breaking the existing stable retrieval contract.

## 2. Design Principles

The implementation must preserve these rules:

1. External embeddings are the preferred path when configured.
2. Local hashed embeddings remain available only as explicit fallback and offline-safe execution support.
3. Provider failure must degrade visibly, not silently.
4. The existing `business_context` contract should remain stable for planner, evaluation, HTML, and dashboard consumers.
5. The repository must not claim a vector database, external indexing service, or guaranteed live provider in every environment.
6. The new code should follow the existing provider style already used by `judge.py`.

## 3. Provider Strategy

Recommended provider mode:

- provider type: `openai_compatible`
- target vendor for this environment: Alibaba Bailian / DashScope compatible embeddings API
- transport: direct HTTP via `httpx`

Why this mode:

- it matches the existing `OpenAICompatibleEvalJudge` pattern already present in the repo
- it keeps the provider boundary generic instead of hard-coding a vendor SDK
- it minimizes new dependencies and reduces contract churn

Not chosen in this slice:

- vendor-native SDK integration
- `openai` Python SDK wrapper layer
- vector database storage or persistent embedding index

## 4. Target Settings Contract

The backend settings should add an explicit embedding provider contract:

```python
embedding_provider: Literal["local", "openai_compatible"] = "local"
embedding_base_url: str | None = None
embedding_api_key: str | None = None
embedding_model: str = "text-embedding-v4"
embedding_timeout_seconds: float = 10.0
```

Behavior rules:

- `embedding_provider=local` keeps the current deterministic retriever path
- `embedding_provider=openai_compatible` enables provider-backed embeddings only when `embedding_base_url` and a usable API key are present
- API key resolution should support:
  - explicit `EMBEDDING_API_KEY`
  - `TONGYI_API_KEY`
  - `DASHSCOPE_API_KEY`
- explicit settings values should win over env alias fallback

This preserves a generic contract while still supporting the user’s current environment.

## 5. Retrieval Runtime Contract

The existing high-level return shape from `retrieve_hybrid_context(...)` should stay stable:

```json
{
  "query": "...",
  "retrieval_mode": "hybrid_keyword_bm25_embedding_rerank",
  "retrievers": ["keyword", "bm25", "embedding"],
  "documents": [...],
  "semantic_memory": {...}
}
```

But embedding-specific metadata should become more explicit inside each embedding-derived hit and at the retrieval level.

Target metadata additions:

- per-hit metadata:
  - `embedding_provider`
  - `embedding_model`
  - `embedding_backend`
  - `used_fallback`
  - `fallback_reason`
- retrieval-level summary:
  - `embedding_runtime`
    - configured_provider
    - effective_provider
    - enabled
    - used_fallback
    - model
    - fallback_reason

This keeps the planner/evaluation contract stable while improving run-level truthfulness.

## 6. Retriever Design

The local retriever should remain intact, but a provider-backed retriever should be added alongside it.

Recommended file boundary:

- keep `backend/app/rag/local_vector_retriever.py` for the current hashed path
- add `backend/app/rag/external_embedding_retriever.py` for provider-backed embeddings
- add a small builder/helper in `backend/app/rag/hybrid_retriever.py` to choose the embedding retriever

### 6.1 External retriever responsibilities

The new retriever should:

- embed the query once
- embed the document corpus once during construction
- compute cosine similarity locally over returned vectors
- preserve current token-overlap blending so retrieval behavior remains comparable to the existing local path
- expose provider metadata on returned results

### 6.2 Failure handling

Provider-backed retrieval may fail for:

- missing `httpx`
- missing base URL
- missing API key
- HTTP timeout
- upstream non-200 response
- malformed response payload

Failure policy:

- if the provider path is not fully configured, use local retrieval directly
- if provider invocation fails at runtime, degrade to local retrieval
- set explicit metadata showing fallback happened and why
- do not surface the run as if provider-backed retrieval succeeded

## 7. Runtime Behavior Changes

`retrieve_hybrid_context(...)` should:

1. build keyword and BM25 hits as before
2. build the embedding retriever from settings
3. run provider-backed embeddings when enabled
4. fall back to local embeddings when the provider is disabled or fails
5. preserve merged rerank behavior and `semantic_memory` generation

The rest of the monitor graph should not require contract changes:

- `nodes.py` keeps reading `retrieve_hybrid_context(...)`
- planner still consumes `business_context`
- evaluation still consumes `business_context.semantic_memory`
- HTML and dashboard continue reading `retrieval_mode`, `retrievers`, and `semantic_memory`

## 8. Documentation Truth Boundary

After implementation, the project may truthfully say:

- the knowledge-base RAG layer supports an optional external embedding provider
- the current environment can prefer a provider-backed embedding call over local hashed embeddings
- provider failures degrade visibly to the local retriever

It still must not say:

- a production vector database is deployed
- external embedding indexing is persisted
- every runtime environment is guaranteed to use Bailian
- the provider path is verified unless the configured environment actually runs it

## 9. File-Level Change Boundary

Expected change surface:

- `backend/app/core/config.py`
- `backend/app/rag/local_vector_retriever.py`
- `backend/app/rag/external_embedding_retriever.py`
- `backend/app/rag/hybrid_retriever.py`
- `backend/tests/test_tools_and_eval.py`
- `backend/tests/test_monitor_run_flow.py`
- `backend/README.md`
- `README.md`
- `docs/resume-alignment.md`
- `PROJECT_TODO.md`

Not in scope:

- new APIs
- frontend visual redesign
- OpenSearch history retrieval changes
- semantic dedup redesign
- provider-backed judge changes

## 10. Test Strategy

The implementation must add or update tests in four groups.

### 10.1 Settings tests

Validate:

- embedding provider values are accepted
- env alias resolution supports `TONGYI_API_KEY` and `DASHSCOPE_API_KEY`
- explicit `embedding_api_key` overrides env aliases

### 10.2 External retriever tests

Validate:

- the retriever calls `/embeddings` with the configured base URL, key, model, and timeout
- query and document vectors are parsed correctly
- provider metadata is attached to results
- runtime errors produce explicit fallback metadata

### 10.3 Hybrid retrieval tests

Validate:

- `retrieve_hybrid_context(...)` keeps the stable top-level contract
- provider-backed embedding hits can participate in reranking
- fallback to local retrieval preserves `semantic_memory` and `documents`
- `embedding_runtime` explains configured vs effective provider

### 10.4 End-to-end run tests

Validate:

- monitor graph still completes
- `business_context` still carries `retrieval_mode`, `retrievers`, `documents`, and `semantic_memory`
- provider-backed metadata can flow into the run snapshot when configured

## 11. Acceptance Criteria

This slice is complete only when all of the following are true:

1. The backend can be configured for `embedding_provider=openai_compatible`.
2. The provider path can consume the user’s current env alias shape without exposing secrets.
3. External embeddings are the primary path when configured.
4. Local hashed embeddings remain available as explicit fallback only.
5. Retrieval output stays contract-compatible for existing planner/evaluation/UI code.
6. Documentation is updated so the repo no longer says “local-only hashed embedding” as the only supported path.

## 12. Out Of Scope Follow-Ups

These remain later-phase work:

- persistent vector indexing
- external vector-store retrieval
- provider-backed semantic history dedup
- dedicated run-detail UI cards for embedding runtime evidence
- live-provider smoke verification against the user’s key in a fully configured backend stack
