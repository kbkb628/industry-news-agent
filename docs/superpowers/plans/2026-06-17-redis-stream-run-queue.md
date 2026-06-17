# Redis Stream Run Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current Redis list-backed run queue with a truthful Redis Stream consumer-group queue while keeping the in-memory fallback for local tests and Redis-unavailable environments.

**Architecture:** `RunQueueProtocol` stays stable for worker callers. `RedisStreamRunQueue` uses `XGROUP CREATE`, `XADD`, `XREADGROUP`, and `XACK` to enqueue, consume, and acknowledge monitor run messages. The existing `InMemoryRunQueue` remains the deterministic fallback and test queue.

**Tech Stack:** Python 3.12, redis-py, pytest, existing FastAPI/LangGraph scheduler worker.

---

### Task 1: Add Redis Stream Queue Contract Tests

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Write failing tests for Redis Stream enqueue/dequeue**

Add a fake Redis stream client that records `xgroup_create`, `xadd`, `xreadgroup`, and `xack`, then assert queue behavior:

```python
def test_redis_stream_run_queue_uses_consumer_group_ack_flow() -> None:
    from app.scheduler.worker import RedisStreamRunQueue

    class FakeRedisStreamClient:
        def __init__(self) -> None:
            self.created_groups: list[dict[str, object]] = []
            self.added: list[dict[str, object]] = []
            self.acked: list[dict[str, object]] = []

        def xgroup_create(self, name: str, groupname: str, id: str, mkstream: bool) -> None:
            self.created_groups.append(
                {"name": name, "groupname": groupname, "id": id, "mkstream": mkstream}
            )

        def xadd(self, name: str, fields: dict[str, str]) -> str:
            self.added.append({"name": name, "fields": fields})
            return "1710000000000-0"

        def xreadgroup(
            self,
            groupname: str,
            consumername: str,
            streams: dict[str, str],
            count: int,
            block: int,
        ) -> list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]:
            return [
                (
                    b"industry_news_agent:run_stream",
                    [
                        (
                            b"1710000000000-0",
                            {
                                b"topic_id": b"topic_ai_agent",
                                b"trigger": b"scheduler",
                                b"enqueued_at": b"2026-06-09T12:00:00Z",
                            },
                        )
                    ],
                )
            ]

        def xack(self, name: str, groupname: str, id: bytes) -> int:
            self.acked.append({"name": name, "groupname": groupname, "id": id})
            return 1

    client = FakeRedisStreamClient()
    queue = RedisStreamRunQueue(
        client,
        stream_key="industry_news_agent:run_stream",
        group_name="monitor-workers",
        consumer_name="worker-1",
    )

    enqueue_result = queue.enqueue(
        RunQueueMessage(
            topic_id="topic_ai_agent",
            trigger="scheduler",
            enqueued_at=datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
        )
    )
    message = queue.dequeue()

    assert enqueue_result["status"] == "queued"
    assert enqueue_result["message_id"] == "1710000000000-0"
    assert message is not None
    assert message.topic_id == "topic_ai_agent"
    assert message.trigger == "scheduler"
    assert client.created_groups == [
        {
            "name": "industry_news_agent:run_stream",
            "groupname": "monitor-workers",
            "id": "0",
            "mkstream": True,
        }
    ]
    assert client.acked == [
        {
            "name": "industry_news_agent:run_stream",
            "groupname": "monitor-workers",
            "id": b"1710000000000-0",
        }
    ]
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `py -3.12 -m pytest tests/test_tools_and_eval.py::test_redis_stream_run_queue_uses_consumer_group_ack_flow -q`

Expected: FAIL because `RedisStreamRunQueue` does not exist.

### Task 2: Implement RedisStreamRunQueue

**Files:**
- Modify: `backend/app/scheduler/worker.py`

- [ ] **Step 1: Add queue implementation**

Implement `RedisStreamRunQueue` beside `InMemoryRunQueue`. It must:

```python
class RedisStreamRunQueue:
    def __init__(
        self,
        redis_client: Any,
        *,
        stream_key: str = "industry_news_agent:run_stream",
        group_name: str = "monitor-workers",
        consumer_name: str = "monitor-worker-1",
        block_ms: int = 0,
    ) -> None: ...
```

Behavior:

```text
__init__ creates the consumer group with mkstream=True.
If Redis reports BUSYGROUP, it is ignored because the group already exists.
enqueue writes topic_id, trigger, and enqueued_at with XADD.
dequeue calls XREADGROUP with stream id ">" and count 1.
dequeue returns None when Redis has no message.
dequeue converts bytes keys/values to strings.
dequeue acknowledges the message with XACK before returning RunQueueMessage.
```

- [ ] **Step 2: Update build_run_queue**

Change `build_run_queue()` so successful Redis connectivity returns `RedisStreamRunQueue(redis_client)` instead of the old list queue.

- [ ] **Step 3: Keep legacy behavior out of the public claim**

Remove or stop using the old `RedisRunQueue` list implementation so README claims and runtime behavior are aligned.

- [ ] **Step 4: Run the focused test**

Run: `py -3.12 -m pytest tests/test_tools_and_eval.py::test_redis_stream_run_queue_uses_consumer_group_ack_flow -q`

Expected: PASS.

### Task 3: Preserve Fallback And Documentation

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/README.md`

- [ ] **Step 1: Keep fallback test green**

Run: `py -3.12 -m pytest tests/test_tools_and_eval.py::test_build_run_queue_falls_back_to_in_memory_when_redis_ping_fails -q`

Expected: PASS.

- [ ] **Step 2: Update README scope**

Move Redis Stream worker groups from "Not claimed" to included capabilities. Keep Playwright MCP, Elasticsearch/vector indexing, LLM-as-Judge, and production hardening as not claimed.

- [ ] **Step 3: Run full backend verification**

Run:

```powershell
cd backend
py -3.12 -m pytest -q
py -3.12 -m compileall app
```

Expected: all tests pass and compileall exits 0.

- [ ] **Step 4: Commit the milestone**

Run:

```powershell
git add backend/app/scheduler/worker.py backend/tests/test_tools_and_eval.py backend/README.md docs/superpowers/plans/2026-06-17-redis-stream-run-queue.md
git commit -m "feat: use redis stream run queue"
git push
```

Expected: branch pushes to `origin/feat/phase2-scheduler-worker`.

