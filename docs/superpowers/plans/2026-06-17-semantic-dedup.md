# Semantic Dedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional deterministic semantic dedup path that clusters near-duplicate article titles and summaries after exact URL/title/fingerprint dedup.

**Architecture:** Preserve the current exact dedup behavior as the default. When explicitly enabled, `DedupCandidatesTool` applies a local token-vector similarity strategy after exact dedup and drops near-duplicates while recording why each item was dropped. This is a local deterministic semantic-like adapter, not an external embedding service or vector database.

**Tech Stack:** Python stdlib tokenization/cosine similarity, Pydantic settings, pytest, existing `DedupCandidatesTool` and `ToolRegistry`.

---

## Guidance Boundaries

- Do not claim external embedding model indexing.
- Do not claim vector database retrieval.
- Do not change default deterministic exact dedup behavior.
- Do not make semantic dedup depend on network, LLM, or external services.
- Keep all dropped candidate ids and reasons visible in tool output metadata/data.

## File Structure

- Modify `backend/app/core/config.py`: add semantic dedup settings.
- Create `backend/app/tools/semantic_dedup.py`: local token-vector similarity strategy.
- Modify `backend/app/tools/dedup_tool.py`: accept optional semantic strategy and append semantic drop reasons.
- Modify `backend/app/tools/registry.py`: wire semantic strategy when enabled by settings.
- Modify `backend/tests/test_tools_and_eval.py`: add settings, strategy, and registry/tool tests.
- Modify `backend/README.md`: truthfully declare optional local semantic-like dedup and keep external embedding/vector claims excluded.

## Task 1: Settings Contract

**Files:**
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_tools_and_eval.py`

- [x] **Step 1: Write failing test**

```python
def test_settings_accept_semantic_dedup_values() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        semantic_dedup_provider="local",
        semantic_dedup_threshold=0.82,
    )

    assert settings.semantic_dedup_provider == "local"
    assert settings.semantic_dedup_threshold == 0.82
```

- [x] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest tests/test_tools_and_eval.py::test_settings_accept_semantic_dedup_values -q`

Expected: FAIL because settings do not exist.

- [x] **Step 3: Write minimal implementation**

```python
semantic_dedup_provider: str = Field(default="none")
semantic_dedup_threshold: float = Field(default=0.88, gt=0.0, le=1.0)
```

- [x] **Step 4: Run test to verify it passes**

Run the same focused test.

Expected: PASS.

## Task 2: Local Semantic Dedup Strategy

**Files:**
- Create: `backend/app/tools/semantic_dedup.py`
- Test: `backend/tests/test_tools_and_eval.py`

- [x] **Step 1: Write failing test**

```python
def test_local_semantic_dedup_drops_similar_title_and_summary() -> None:
    from app.tools.semantic_dedup import LocalSemanticDedupStrategy

    strategy = LocalSemanticDedupStrategy(threshold=0.55)
    articles = [
        {
            "candidate_id": "cand_a",
            "title": "OpenAI launches enterprise agent workflow",
            "summary": "OpenAI released an enterprise agent automation workflow.",
        },
        {
            "candidate_id": "cand_b",
            "title": "OpenAI releases enterprise agent workflow",
            "summary": "OpenAI launched an enterprise workflow for agent automation.",
        },
        {
            "candidate_id": "cand_c",
            "title": "Chip startup raises new funding",
            "summary": "A semiconductor startup announced funding.",
        },
    ]

    result = strategy.deduplicate(articles)

    assert [item["candidate_id"] for item in result.kept_articles] == ["cand_a", "cand_c"]
    assert result.dropped_candidate_ids == ["cand_b"]
    assert result.drop_reasons["cand_b"]["reason"] == "semantic_similarity"
    assert result.drop_reasons["cand_b"]["matched_candidate_id"] == "cand_a"
```

- [x] **Step 2: Run test to verify it fails**

Run the focused test.

Expected: FAIL because the module does not exist.

- [x] **Step 3: Write minimal implementation**

Implement:

- `SemanticDedupResult`
- `LocalSemanticDedupStrategy`
- tokenization over `title`, `summary`, `raw_summary`, and `content`
- cosine similarity over token count vectors
- keep first item in order, drop later items above threshold

- [x] **Step 4: Run test to verify it passes**

Run the focused test.

Expected: PASS.

## Task 3: Dedup Tool Integration

**Files:**
- Modify: `backend/app/tools/dedup_tool.py`
- Modify: `backend/app/tools/registry.py`
- Test: `backend/tests/test_tools_and_eval.py`

- [x] **Step 1: Write failing tests**

```python
def test_dedup_tool_applies_semantic_strategy_after_exact_dedup() -> None:
    from app.tools.dedup_tool import DedupCandidatesTool
    from app.tools.semantic_dedup import LocalSemanticDedupStrategy

    tool = DedupCandidatesTool(
        semantic_strategy=LocalSemanticDedupStrategy(threshold=0.55)
    )

    response = tool(
        articles=[
            {
                "candidate_id": "cand_a",
                "title": "OpenAI launches enterprise agent workflow",
                "url": "https://example.com/a",
                "summary": "OpenAI released an enterprise agent automation workflow.",
                "content": "OpenAI released an enterprise agent automation workflow.",
            },
            {
                "candidate_id": "cand_b",
                "title": "OpenAI releases enterprise agent workflow",
                "url": "https://example.com/b",
                "summary": "OpenAI launched an enterprise workflow for agent automation.",
                "content": "OpenAI launched an enterprise workflow for agent automation.",
            },
        ],
    )

    assert [item["candidate_id"] for item in response.data["articles"]] == ["cand_a"]
    assert response.data["dropped_candidate_ids"] == ["cand_b"]
    assert response.data["semantic_dropped_candidate_ids"] == ["cand_b"]
    assert response.metadata["semantic_dedup_provider"] == "local"
```

```python
def test_build_default_tool_registry_enables_local_semantic_dedup() -> None:
    from app.tools.registry import build_default_tool_registry

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        semantic_dedup_provider="local",
        semantic_dedup_threshold=0.55,
    )
    registry = build_default_tool_registry(llm=MockLLM(), settings=settings)
    gateway = LocalToolGateway()
    registry.register_into(gateway)

    response = gateway.call(
        "deduplicate_items",
        articles=[
            {
                "candidate_id": "cand_a",
                "title": "OpenAI launches enterprise agent workflow",
                "url": "https://example.com/a",
                "summary": "OpenAI released an enterprise agent automation workflow.",
                "content": "OpenAI released an enterprise agent automation workflow.",
            },
            {
                "candidate_id": "cand_b",
                "title": "OpenAI releases enterprise agent workflow",
                "url": "https://example.com/b",
                "summary": "OpenAI launched an enterprise workflow for agent automation.",
                "content": "OpenAI launched an enterprise workflow for agent automation.",
            },
        ],
    )

    assert response.metadata["semantic_dedup_provider"] == "local"
    assert response.data["semantic_dropped_candidate_ids"] == ["cand_b"]
```

- [x] **Step 2: Run tests to verify they fail**

Run both focused tests.

Expected: FAIL because `DedupCandidatesTool` does not accept a semantic strategy yet.

- [x] **Step 3: Write minimal implementation**

Update `DedupCandidatesTool` to:

- accept `semantic_strategy=None`
- run exact dedup first
- run semantic strategy over exact-kept articles when configured
- merge exact and semantic dropped ids
- expose unified `drop_reasons`, plus `semantic_dropped_candidate_ids` and
  `semantic_drop_reasons`
- set metadata `semantic_dedup_provider`

Update registry to enable `LocalSemanticDedupStrategy` only when `settings.semantic_dedup_provider == "local"`.

- [x] **Step 4: Run tests to verify they pass**

- [x] **Step 5: Address review hardening**

Add tests and implementation for:

- invalid semantic thresholds rejected at settings load time
- default registry path keeps semantic dedup disabled
- exact and semantic drops both remain visible through a unified `drop_reasons`
  response field
- missing `candidate_id` under semantic dedup returns a tool failure through
  `LocalToolGateway`

Run focused tests.

Expected: PASS.

## Task 4: Documentation And Verification

**Files:**
- Modify: `backend/README.md`

- [x] **Step 1: Update README**

Add included capability:

- optional deterministic local semantic-like dedup after exact dedup

Keep not claimed:

- external embedding indexing
- vector database retrieval
- production semantic clustering service

- [x] **Step 2: Run verification**

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

- [x] **Step 3: Commit and push**

```powershell
git add docs/superpowers/plans/2026-06-17-semantic-dedup.md backend/app/core/config.py backend/app/tools/semantic_dedup.py backend/app/tools/dedup_tool.py backend/app/tools/registry.py backend/tests/test_tools_and_eval.py backend/README.md
git commit -m "feat: add local semantic dedup"
git push
```
