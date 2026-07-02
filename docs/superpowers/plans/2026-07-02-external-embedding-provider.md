# External Embedding Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an external-first embedding provider path to the backend RAG retrieval layer while preserving the current business-context contract and explicit local fallback behavior.

**Architecture:** Keep keyword and BM25 retrieval unchanged, add a provider-backed embedding retriever behind an OpenAI-compatible HTTP boundary, and let `retrieve_hybrid_context(...)` choose external embeddings first when configured. Preserve `business_context.documents`, `semantic_memory`, and rerank behavior, while adding runtime metadata that makes provider usage and fallback visible.

**Tech Stack:** Python 3.12, FastAPI backend, LangGraph monitor flow, `httpx`, pytest, Pydantic settings

---

### Task 1: Freeze Settings And Env Alias Support

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Write the failing settings tests**

Add tests to `backend/tests/test_tools_and_eval.py` that assert the new provider settings and env aliases work:

```python
def test_settings_accept_external_embedding_provider_values() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        embedding_provider="openai_compatible",
        embedding_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        embedding_api_key="test-key",
        embedding_model="text-embedding-v4",
        embedding_timeout_seconds=4.0,
    )

    assert settings.embedding_provider == "openai_compatible"
    assert settings.embedding_base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert settings.embedding_api_key == "test-key"
    assert settings.embedding_model == "text-embedding-v4"
    assert settings.embedding_timeout_seconds == 4.0


def test_settings_resolve_embedding_api_key_from_tongyi_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TONGYI_API_KEY", "tongyi-test-key")

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        embedding_provider="openai_compatible",
        embedding_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    assert settings.embedding_api_key == "tongyi-test-key"


def test_settings_explicit_embedding_api_key_overrides_alias_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TONGYI_API_KEY", "tongyi-test-key")

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        embedding_provider="openai_compatible",
        embedding_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        embedding_api_key="explicit-key",
    )

    assert settings.embedding_api_key == "explicit-key"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest backend/tests/test_tools_and_eval.py -q -k "embedding_provider or tongyi_alias"`

Expected: FAIL because `Settings` does not yet define the embedding provider fields or env alias behavior.

- [ ] **Step 3: Implement the settings contract**

Update `backend/app/core/config.py` to add:

```python
from pydantic import Field, model_validator
```

and add fields:

```python
    embedding_provider: Literal["local", "openai_compatible"] = Field(default="local")
    embedding_base_url: str | None = Field(default=None)
    embedding_api_key: str | None = Field(default=None)
    embedding_model: str = Field(default="text-embedding-v4")
    embedding_timeout_seconds: float = Field(default=10.0, gt=0.0)
```

Then add a post-validation alias resolver:

```python
    @model_validator(mode="after")
    def resolve_embedding_api_key_aliases(self) -> "Settings":
        if self.embedding_api_key:
            return self

        import os

        for alias in ("TONGYI_API_KEY", "DASHSCOPE_API_KEY"):
            value = os.getenv(alias)
            if value:
                self.embedding_api_key = value
                break
        return self
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.12 -m pytest backend/tests/test_tools_and_eval.py -q -k "embedding_provider or tongyi_alias"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/tests/test_tools_and_eval.py
git commit -m "feat: add external embedding settings contract"
```

### Task 2: Add The External Embedding Retriever With Provider Metadata

**Files:**
- Create: `backend/app/rag/external_embedding_retriever.py`
- Modify: `backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Write the failing external retriever tests**

Add tests that assert a provider-backed retriever calls `/embeddings` and returns provider metadata:

```python
def test_external_embedding_retriever_calls_openai_compatible_embeddings() -> None:
    documents = [
        KnowledgeDocument(
            doc_id="kb_001",
            title="AI agent launch",
            content="OpenAI launched enterprise agent tooling.",
            keywords=["AI", "agent"],
            metadata={},
        )
    ]

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "data": [
                    {"embedding": [0.8, 0.2]},
                    {"embedding": [0.9, 0.1]},
                ]
            }

    class FakeHttpClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def post(self, url: str, headers: dict[str, str], json: dict[str, object], timeout: float) -> FakeResponse:
            self.requests.append(
                {"url": url, "headers": headers, "json": json, "timeout": timeout}
            )
            return FakeResponse()

    retriever = OpenAICompatibleEmbeddingRetriever(
        documents,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="test-key",
        model="text-embedding-v4",
        timeout_seconds=4.0,
        http_client=FakeHttpClient(),
    )

    results = retriever.retrieve("enterprise agent", top_k=1)

    assert results[0].metadata["embedding_backend"] == "openai_compatible"
    assert results[0].metadata["embedding_provider"] == "external"
    assert results[0].metadata["embedding_model"] == "text-embedding-v4"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest backend/tests/test_tools_and_eval.py -q -k "external_embedding_retriever_calls_openai_compatible_embeddings"`

Expected: FAIL because the retriever does not yet exist.

- [ ] **Step 3: Implement the new retriever**

Create `backend/app/rag/external_embedding_retriever.py` with:

- a result dataclass mirroring the local retriever result shape
- `OpenAICompatibleEmbeddingRetriever`
- helper methods to:
  - build the embed input strings from title/content/keywords
  - call `POST {base_url}/embeddings`
  - parse the `data[*].embedding` array
  - compute cosine similarity
  - blend embedding score with the existing canonical token-overlap signal

The class should attach metadata like:

```python
{
    "retriever": "embedding",
    "embedding_provider": "external",
    "embedding_backend": "openai_compatible",
    "embedding_model": self.model,
    "used_fallback": False,
    "fallback_reason": None,
}
```

Use direct `httpx` import fallback behavior consistent with `judge.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.12 -m pytest backend/tests/test_tools_and_eval.py -q -k "external_embedding_retriever_calls_openai_compatible_embeddings"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/external_embedding_retriever.py backend/tests/test_tools_and_eval.py
git commit -m "feat: add external embedding retriever"
```

### Task 3: Switch Hybrid Retrieval To External-First With Explicit Fallback

**Files:**
- Modify: `backend/app/rag/hybrid_retriever.py`
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/tests/test_monitor_run_flow.py`

- [ ] **Step 1: Write the failing hybrid retrieval tests**

Add tests for provider-first behavior and explicit fallback:

```python
def test_retrieve_hybrid_context_uses_external_embedding_provider_when_configured() -> None:
    documents = [
        KnowledgeDocument(
            doc_id="kb_001",
            title="AI agent launch",
            content="OpenAI launched enterprise agent tooling.",
            keywords=["AI", "agent"],
            metadata={"topic_keywords": ["AI Agent"]},
        )
    ]

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        embedding_provider="openai_compatible",
        embedding_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        embedding_api_key="test-key",
        embedding_model="text-embedding-v4",
    )

    context = retrieve_hybrid_context(
        documents,
        "enterprise agent",
        top_k=1,
        settings=settings,
        embedding_http_client=FakeEmbeddingHttpClient(),
    )

    assert context["embedding_runtime"]["configured_provider"] == "openai_compatible"
    assert context["embedding_runtime"]["effective_provider"] == "openai_compatible"
    assert context["embedding_runtime"]["used_fallback"] is False
    assert context["documents"][0]["scores"]["embedding"] > 0


def test_retrieve_hybrid_context_falls_back_to_local_embedding_when_provider_fails() -> None:
    documents = [
        KnowledgeDocument(
            doc_id="kb_001",
            title="AI agent launch",
            content="OpenAI launched enterprise agent tooling.",
            keywords=["AI", "agent"],
            metadata={"topic_keywords": ["AI Agent"]},
        )
    ]

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        embedding_provider="openai_compatible",
        embedding_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        embedding_api_key="test-key",
        embedding_model="text-embedding-v4",
    )

    class FailingHttpClient:
        def post(self, *args, **kwargs):
            raise RuntimeError("provider unavailable")

    context = retrieve_hybrid_context(
        documents,
        "enterprise agent",
        top_k=1,
        settings=settings,
        embedding_http_client=FailingHttpClient(),
    )

    assert context["embedding_runtime"]["configured_provider"] == "openai_compatible"
    assert context["embedding_runtime"]["effective_provider"] == "local"
    assert context["embedding_runtime"]["used_fallback"] is True
    assert "provider unavailable" in context["embedding_runtime"]["fallback_reason"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py -q -k "embedding_runtime or falls_back_to_local_embedding"`

Expected: FAIL because `retrieve_hybrid_context(...)` has no provider-selection or runtime summary support yet.

- [ ] **Step 3: Implement provider selection and fallback**

Update `backend/app/rag/hybrid_retriever.py` to:

- accept an optional `embedding_http_client` parameter for tests
- build the local retriever exactly as today
- if `settings.embedding_provider == "openai_compatible"` and required config exists:
  - try `OpenAICompatibleEmbeddingRetriever`
  - use its results on success
  - on failure, fall back to `LocalVectorRetriever`
- otherwise, use `LocalVectorRetriever`

Add an `embedding_runtime` block to the returned context:

```python
{
    "configured_provider": settings.embedding_provider if settings else "local",
    "effective_provider": effective_provider,
    "enabled": embedding_enabled,
    "used_fallback": used_fallback,
    "model": effective_model,
    "fallback_reason": fallback_reason,
}
```

Keep `retrieval_mode`, `retrievers`, `documents`, and `semantic_memory` unchanged at the top level.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.12 -m pytest backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py -q -k "embedding_runtime or falls_back_to_local_embedding"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/hybrid_retriever.py backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py
git commit -m "feat: add external-first embedding retrieval fallback"
```

### Task 4: Update Documentation And Close The Milestone

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `docs/resume-alignment.md`
- Modify: `PROJECT_TODO.md`

- [ ] **Step 1: Update docs to reflect the new truth boundary**

Update the root README, backend README, and resume-alignment doc so they no longer describe the repo as local hashed-embedding only. The new wording should say:

- external embedding provider support now exists as an optional boundary
- current preferred direction is external-first when configured
- local hashed embeddings remain explicit fallback only
- this still does not imply a vector database or always-live provider

- [ ] **Step 2: Update milestone tracking**

Update `PROJECT_TODO.md` so this slice is recorded with one in-progress item while coding and a completed item once tests pass:

- `spec and planning for external embedding provider`
- `implement external-first embedding provider path`

- [ ] **Step 3: Run focused verification**

Run: `py -3.12 -m pytest backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py backend/tests/test_topics_api.py backend/tests/test_health_api.py -q`

Expected: PASS

- [ ] **Step 4: Run repo hygiene verification**

Run: `git diff --check`

Expected: no output

- [ ] **Step 5: Commit**

```bash
git add README.md backend/README.md docs/resume-alignment.md PROJECT_TODO.md
git commit -m "docs: align external embedding provider truth boundary"
```

## Self-Review

### Spec coverage

- settings and env alias support are implemented in Task 1
- provider-backed retrieval is implemented in Task 2
- external-first hybrid selection and fallback are implemented in Task 3
- docs and milestone closure are implemented in Task 4

### Placeholder scan

- no `TBD`, `TODO`, or vague “handle later” placeholders are present
- every task includes exact files and verification commands

### Type consistency

- the plan consistently uses `embedding_provider`, `embedding_base_url`, `embedding_api_key`, `embedding_model`, and `embedding_timeout_seconds`
- the runtime summary consistently uses `embedding_runtime`
