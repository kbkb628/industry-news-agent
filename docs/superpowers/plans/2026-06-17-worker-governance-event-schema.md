# Worker Governance Event Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the event API schema compatible with worker governance events emitted by the Redis Stream worker path.

**Architecture:** The worker already persists queue and governance events for dequeue, retry, timeout, active-run skips, and failures. This compatibility slice only extends the constrained event response enums so those persisted events remain queryable through `/api/monitor/runs/{run_id}/events`.

**Tech Stack:** FastAPI, Pydantic, pytest.

---

### Task 1: Accept Worker Governance Event Types And Nodes

**Files:**
- Modify: `backend/app/schemas/event_schema.py`
- Test: `backend/tests/test_supporting_schema_contracts.py`

- [ ] **Step 1: Write the failing test**

Add a parameterized schema test for the worker event types and node names already emitted by `backend/app/scheduler/worker.py`:

```python
@pytest.mark.parametrize(
    ("event_type", "node"),
    [
        ("queue_dequeued", "worker_dequeue"),
        ("governance_retry", "worker_retry"),
        ("governance_timeout", "worker_timeout"),
        ("governance_skipped", "worker_active_run_guard"),
        ("governance_failed", "worker_failed"),
    ],
)
def test_event_schema_accepts_worker_governance_events(
    event_type: str,
    node: str,
) -> None:
    event = EventRecord(
        event_id=f"event_{node}",
        run_id="run_001",
        topic_id="topic_001",
        event_type=event_type,
        node=node,
        message="Worker governance event.",
        payload={"queue_wait_ms": 12},
    )

    response = EventListResponse(run_id="run_001", events=[event])

    assert response.events[0].event_type == event_type
    assert response.events[0].node == node
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_supporting_schema_contracts.py::test_event_schema_accepts_worker_governance_events -q
```

Expected: FAIL because `EventType` and `MonitorNodeName` do not accept worker governance values.

- [ ] **Step 3: Write minimal implementation**

Add enum members only for the runtime values already emitted by `MonitorWorkerService`:

```python
class EventType(StrEnum):
    ...
    QUEUE_DEQUEUED = "queue_dequeued"
    GOVERNANCE_RETRY = "governance_retry"
    GOVERNANCE_TIMEOUT = "governance_timeout"
    GOVERNANCE_SKIPPED = "governance_skipped"
    GOVERNANCE_FAILED = "governance_failed"


class MonitorNodeName(StrEnum):
    ...
    WORKER_DEQUEUE = "worker_dequeue"
    WORKER_RETRY = "worker_retry"
    WORKER_TIMEOUT = "worker_timeout"
    WORKER_ACTIVE_RUN_GUARD = "worker_active_run_guard"
    WORKER_FAILED = "worker_failed"
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_supporting_schema_contracts.py tests/test_monitor_run_flow.py::test_worker_skips_duplicate_active_run_for_same_topic tests/test_monitor_run_flow.py::test_worker_retries_once_before_marking_run_failed tests/test_monitor_run_flow.py::test_worker_times_out_and_marks_failed_run -q
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
git add docs/superpowers/plans/2026-06-17-worker-governance-event-schema.md backend/tests/test_supporting_schema_contracts.py backend/app/schemas/event_schema.py
git commit -m "fix: accept worker governance events"
git push
```
