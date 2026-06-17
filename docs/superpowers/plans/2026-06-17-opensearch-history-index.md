# OpenSearch History Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional OpenSearch-compatible candidate history index adapter for Phase 2 historical full-text retrieval and dedup support boundaries.

**Architecture:** Keep the monitor graph and dedup tool deterministic by default. Candidate persistence remains the source of truth in PostgreSQL; the external search index is an optional projection built after a run completes. Index failures must be visible in events/errors but must not turn a completed monitor run into a crash.

**Tech Stack:** FastAPI backend, Pydantic settings, httpx-compatible client injection, pytest fake clients, existing monitor repository and event model.

---

## Guidance Boundaries

- Do not claim Elasticsearch/OpenSearch production deployment hardening.
- Do not claim real vector database or external embedding service.
- Do not replace the current deterministic dedup tool in this slice.
- Do not make OpenSearch required for tests or local mock mode.
- Keep the adapter OpenSearch-compatible HTTP, with fake clients for tests.

## File Structure

- Modify `backend/app/core/config.py`: add optional search-index provider settings.
- Create `backend/app/search/history_index.py`: define index document builder, no-op index, OpenSearch-compatible index client, and builder.
- Modify `backend/app/agent/nodes.py`: index persisted candidate records after candidate persistence when enabled; record explicit events.
- Modify `backend/app/agent/graph.py`: pass `settings` into the node path that needs the index builder if necessary.
- Modify `backend/tests/test_tools_and_eval.py`: add adapter and settings tests.
- Modify `backend/tests/test_monitor_run_flow.py`: add monitor graph indexing event tests.
- Modify `backend/README.md`: truthfully declare the optional external history full-text index path and keep vector/embedding and production hardening as not claimed.

## Task 1: Settings Contract

**Files:**
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Write the failing test**

```python
def test_settings_accept_history_index_provider_values() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        history_index_provider="opensearch",
        opensearch_base_url="http://localhost:9200",
        opensearch_index_name="industry-news-candidates",
        opensearch_timeout_seconds=4.0,
    )

    assert settings.history_index_provider == "opensearch"
    assert settings.opensearch_base_url == "http://localhost:9200"
    assert settings.opensearch_index_name == "industry-news-candidates"
    assert settings.opensearch_timeout_seconds == 4.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest tests/test_tools_and_eval.py::test_settings_accept_history_index_provider_values -q`

Expected: FAIL because the settings do not exist.

- [ ] **Step 3: Write minimal implementation**

Add fields:

```python
history_index_provider: str = Field(default="none")
opensearch_base_url: str | None = Field(default=None)
opensearch_index_name: str = Field(default="industry-news-candidates")
opensearch_timeout_seconds: float = Field(default=10.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.12 -m pytest tests/test_tools_and_eval.py::test_settings_accept_history_index_provider_values -q`

Expected: PASS.

## Task 2: OpenSearch-Compatible Index Adapter

**Files:**
- Create: `backend/app/search/history_index.py`
- Test: `backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Write failing tests**

```python
def test_opensearch_history_index_posts_candidate_documents() -> None:
    from app.search.history_index import OpenSearchHistoryIndex

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def put(self, url: str, **kwargs: object) -> FakeResponse:
            self.requests.append({"url": url, **kwargs})
            return FakeResponse()

    client = FakeClient()
    index = OpenSearchHistoryIndex(
        base_url="http://localhost:9200",
        index_name="industry-news-candidates",
        http_client=client,
        timeout_seconds=3.0,
    )

    result = index.index_candidates(
        [
            {
                "candidate_id": "cand_001",
                "run_id": "run_001",
                "topic_id": "topic_ai",
                "source_type": "search",
                "source_name": "OpenWebSearch",
                "title": "OpenAI ships agent workflow",
                "url": "https://example.com/agent",
                "raw_summary": "Agent workflow update.",
                "content": "Full article body.",
                "score": 0.91,
                "decision": "push",
                "decision_reason": "Above threshold",
            }
        ]
    )

    assert result == {"indexed_count": 1, "provider": "opensearch"}
    assert client.requests[0]["url"] == (
        "http://localhost:9200/industry-news-candidates/_doc/run_001-cand_001"
    )
    assert client.requests[0]["timeout"] == 3.0
    assert client.requests[0]["json"]["title"] == "OpenAI ships agent workflow"
    assert client.requests[0]["json"]["content"] == "Full article body."
```

```python
def test_build_history_index_returns_noop_without_complete_opensearch_settings() -> None:
    from app.search.history_index import NoopHistoryIndex, build_history_index

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        history_index_provider="opensearch",
        opensearch_base_url=None,
    )

    assert isinstance(build_history_index(settings=settings), NoopHistoryIndex)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.12 -m pytest tests/test_tools_and_eval.py::test_opensearch_history_index_posts_candidate_documents tests/test_tools_and_eval.py::test_build_history_index_returns_noop_without_complete_opensearch_settings -q`

Expected: FAIL because `app.search.history_index` does not exist.

- [ ] **Step 3: Write minimal implementation**

Create:

- `HistoryIndexProtocol`
- `NoopHistoryIndex.index_candidates(...) -> {"indexed_count": 0, "provider": "none"}`
- `OpenSearchHistoryIndex.index_candidates(...)`
- `build_history_index(settings, http_client=None)`

The OpenSearch adapter must:

- use `PUT {base_url}/{index_name}/_doc/{run_id}-{candidate_id}`
- send a JSON document containing run/topic/source/title/url/summary/content/score/decision fields
- use the configured timeout
- raise provider errors so the graph can record them

- [ ] **Step 4: Run tests to verify they pass**

Run the same focused tests.

Expected: PASS.

## Task 3: Monitor Graph Indexing Event

**Files:**
- Modify: `backend/app/agent/nodes.py`
- Test: `backend/tests/test_monitor_run_flow.py`

- [ ] **Step 1: Write failing test**

Add a test that runs `evaluate_run_node` with a fake repository, `Settings(history_index_provider="opensearch", opensearch_base_url="http://localhost:9200")`, and a fake index HTTP client injected into the node. After evaluation:

- `state["history_index_result"] == {"indexed_count": <candidate count>, "provider": "opensearch"}`
- events include node `index_history` with `indexed_count`
- candidate records are still persisted first

- [ ] **Step 2: Run test to verify it fails**

Run the focused test.

Expected: FAIL because evaluation does not index history.

- [ ] **Step 3: Write minimal implementation**

Update `evaluate_run_node` to accept optional `history_index` or `history_index_http_client` and settings. After `upsert_candidate_records`, build/call the index only when enabled. On success append `index_history` event. On provider exception append a failed `index_history` event and add an error entry, but keep run status completed.

- [ ] **Step 4: Run test to verify it passes**

Run the focused test.

Expected: PASS.

## Task 4: Documentation And Verification

**Files:**
- Modify: `backend/README.md`

- [ ] **Step 1: Update README**

Move only this capability into included scope:

- optional OpenSearch-compatible candidate history full-text index projection

Keep not claimed:

- real vector retrieval or vector database
- embedding indexing with external model embeddings
- production OpenSearch/Elasticsearch cluster hardening

- [ ] **Step 2: Run verification**

From `backend`:

```powershell
py -3.12 -m pytest -q
py -3.12 -m compileall app
```

From repo root:

```powershell
docker compose config --quiet
git diff --check
git status --short --branch
```

- [ ] **Step 3: Commit and push**

```powershell
git add docs/superpowers/plans/2026-06-17-opensearch-history-index.md backend/app/core/config.py backend/app/search/history_index.py backend/app/agent/nodes.py backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py backend/README.md
git commit -m "feat: add opensearch history index adapter"
git push
```

