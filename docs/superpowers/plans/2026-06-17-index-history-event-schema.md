# Index History Event Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the event API schema compatible with the existing OpenSearch history-index event emitted by the monitor graph.

**Architecture:** This is a schema compatibility fix only. The runtime already emits `node="index_history"` events when optional history indexing is enabled, so the API response model must accept that node without widening unrelated contracts.

**Tech Stack:** FastAPI, Pydantic, pytest.

---

### Task 1: Accept History Index Trace Node

**Files:**
- Modify: `backend/app/schemas/event_schema.py`
- Test: `backend/tests/test_supporting_schema_contracts.py`

- [ ] **Step 1: Write the failing test**

Add a test proving `EventListResponse` accepts an OpenSearch history-index trace event:

```python
def test_event_schema_accepts_history_index_node() -> None:
    event = EventRecord(
        event_id="event_index_history_001",
        run_id="run_001",
        topic_id="topic_001",
        event_type="node_completed",
        node="index_history",
        message="Indexed pushed candidates into the history index.",
        payload={"provider": "opensearch", "indexed_count": 1},
    )

    response = EventListResponse(run_id="run_001", events=[event])

    assert response.events[0].event_type == "node_completed"
    assert response.events[0].node == "index_history"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_supporting_schema_contracts.py::test_event_schema_accepts_history_index_node -q
```

Expected: FAIL because `MonitorNodeName` does not accept `index_history`.

- [ ] **Step 3: Write minimal implementation**

Add one enum member:

```python
class MonitorNodeName(StrEnum):
    ...
    INDEX_HISTORY = "index_history"
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_supporting_schema_contracts.py -q
```

Expected: PASS.

- [ ] **Step 5: Run full verification**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest -q
py -3.12 -m compileall app
cd E:\bgagent2\.worktrees\feat-industry-news-mvp
docker compose config --quiet
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit and push**

Run:

```powershell
git add docs/superpowers/plans/2026-06-17-index-history-event-schema.md backend/tests/test_supporting_schema_contracts.py backend/app/schemas/event_schema.py
git commit -m "fix: accept history index events"
git push
```
