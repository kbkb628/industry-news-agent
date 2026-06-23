# Resume Tech Alignment Phase A Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the resume-listed infrastructure technologies `PostgreSQL`, `Redis`, `APScheduler`, `Redis Stream`, and `Elasticsearch` real, verifiable runtime responsibilities in the current project instead of partial or boundary-only capabilities.

**Architecture:** Keep the existing FastAPI single-process topology and current module boundaries. Strengthen the durable store, coordination layer, scheduler lifecycle, stream-backed queue semantics, and search projection/query path in place rather than introducing a new infrastructure abstraction. Use tests to lock each responsibility before changing implementation, and only then update docs/runtime evidence.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, PostgreSQL, Redis, APScheduler, Redis Streams, OpenSearch/Elasticsearch-compatible HTTP APIs, pytest, Docker Compose

---

### Task 1: Tighten PostgreSQL As The Durable Source Of Truth

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/tests/test_monitor_run_flow.py`
- Modify: `backend/app/storage/models.py`
- Modify: `backend/app/storage/repository.py`
- Modify: `backend/app/api/candidates.py`
- Modify: `backend/app/api/events.py`
- Modify: `backend/app/api/pushes.py`
- Modify: `backend/app/api/eval.py`
- Modify: `backend/README.md`

- [ ] **Step 1: Write the failing PostgreSQL durability tests**

Add the following tests to `backend/tests/test_tools_and_eval.py`:

```python
def test_sqlalchemy_repository_round_trips_all_phase_a_entities(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'phase_a_foundation.db'}"
    settings = Settings(
        database_url=database_url,
        redis_url="redis://localhost:6379/0",
    )
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    session = build_session_factory(engine)()
    try:
        topic_repository = build_topic_repository(session)
        run_repository = build_monitor_run_repository(session)

        topic = topic_repository.create_topic(
            TopicCreateData(
                name="AI Agent",
                description="Track enterprise AI agent launches.",
                seed_keywords=("OpenAI", "LangGraph"),
                trusted_sources=("example.com",),
                exclude_keywords=("rumor",),
                push_threshold=0.72,
                cooldown_hours=24,
                enabled=True,
                schedule_cron="0 */6 * * *",
            )
        )

        run_repository.upsert_monitor_run(
            MonitorRunUpsertData(
                run_id="run_phase_a",
                topic_id=topic.topic_id,
                status="completed",
                state_snapshot={
                    "run_id": "run_phase_a",
                    "topic_id": topic.topic_id,
                    "trigger": "scheduler",
                    "status": "completed",
                },
                error_summary=None,
                started_at=datetime(2026, 6, 24, 8, 0, tzinfo=UTC),
                finished_at=datetime(2026, 6, 24, 8, 1, tzinfo=UTC),
            )
        )
        run_repository.upsert_candidate_records(
            (
                CandidateRecordUpsertData(
                    candidate_id="cand_001",
                    run_id="run_phase_a",
                    topic_id=topic.topic_id,
                    source_type="search",
                    source_name="Mock Search",
                    title="OpenAI agent update",
                    url="https://example.com/agent-update",
                    published_at=datetime(2026, 6, 24, 7, 50, tzinfo=UTC),
                    raw_summary="summary",
                    fetch_status="fetched",
                    content="full content",
                    structured_payload={"title": "OpenAI agent update"},
                    score=0.88,
                    decision="push",
                    decision_reason="Above threshold",
                ),
            )
        )
        run_repository.upsert_extracted_item_records(
            (
                ExtractedItemRecordUpsertData(
                    extracted_id="ext_001",
                    run_id="run_phase_a",
                    topic_id=topic.topic_id,
                    candidate_id="cand_001",
                    source_type="search",
                    source_name="Mock Search",
                    title="OpenAI agent update",
                    url="https://example.com/agent-update",
                    published_at=datetime(2026, 6, 24, 7, 50, tzinfo=UTC),
                    summary="summary",
                    keywords=("OpenAI", "agent"),
                    content="full content",
                    content_fingerprint="fp_001",
                    fetch_status="fetched",
                    fetch_error=None,
                    extraction_mode="structured",
                    structured_payload={"entities": ["OpenAI"]},
                ),
            )
        )
        run_repository.upsert_decision_records(
            (
                DecisionRecordUpsertData(
                    decision_id="dec_001",
                    run_id="run_phase_a",
                    topic_id=topic.topic_id,
                    candidate_id="cand_001",
                    extracted_id="ext_001",
                    source_type="search",
                    source_name="Mock Search",
                    title="OpenAI agent update",
                    url="https://example.com/agent-update",
                    published_at=datetime(2026, 6, 24, 7, 50, tzinfo=UTC),
                    summary="summary",
                    score=0.88,
                    should_push=True,
                    decision_reason="Above threshold",
                    decision_payload={"score_breakdown": "trusted source"},
                ),
            )
        )
        run_repository.create_push_records(
            (
                PushRecordCreateData(
                    run_id="run_phase_a",
                    topic_id=topic.topic_id,
                    candidate_id="cand_001",
                    extracted_id="ext_001",
                    title="OpenAI agent update",
                    url="https://example.com/agent-update",
                    summary="summary",
                    should_push=True,
                    score=0.88,
                    decision_reason="Above threshold",
                    pushed_at=datetime(2026, 6, 24, 8, 1, tzinfo=UTC),
                ),
            )
        )
        run_repository.create_run_events(
            (
                RunEventCreateData(
                    run_id="run_phase_a",
                    topic_id=topic.topic_id,
                    event_type="run_completed",
                    node="supervisor_finalize",
                    message="Run completed.",
                    payload={"status": "completed"},
                    elapsed_ms=3210,
                ),
            )
        )
        run_repository.create_eval_result(
            EvalResultCreateData(
                run_id="run_phase_a",
                topic_id=topic.topic_id,
                retrieved_count=1,
                deduped_count=1,
                dedup_rate=0.0,
                push_count=1,
                duplicate_push_count=0,
                tool_success_rate=1.0,
                fetch_success_rate=1.0,
                trace_completeness=1.0,
                raw_summary_count=0,
                browser_fallback_count=0,
                provider_fallback_count=0,
            )
        )

        assert run_repository.get_monitor_run("run_phase_a") is not None
        assert len(run_repository.list_candidate_records("run_phase_a")) == 1
        assert len(run_repository.list_extracted_item_records("run_phase_a")) == 1
        assert len(run_repository.list_decision_records("run_phase_a")) == 1
        assert len(run_repository.list_push_records(run_id="run_phase_a")) == 1
        assert len(run_repository.list_run_events("run_phase_a")) == 1
        assert run_repository.get_eval_result("run_phase_a") is not None
    finally:
        session.close()
        engine.dispose()


def test_monitor_detail_endpoints_read_persisted_phase_a_entities(client: TestClient) -> None:
    topic_response = client.post(
        "/api/topics",
        json={
            "name": "AI Agent",
            "description": "Track enterprise AI agent launches.",
            "seed_keywords": ["OpenAI", "LangGraph"],
            "trusted_sources": ["example.com"],
            "exclude_keywords": ["rumor"],
            "push_threshold": 0.72,
            "cooldown_hours": 24,
            "enabled": True,
            "schedule_cron": "0 */6 * * *",
        },
    )
    topic_id = topic_response.json()["topic_id"]

    run_response = client.post(f"/api/monitor/{topic_id}/run")
    assert run_response.status_code == 200
    run_id = run_response.json()["run_id"]

    run_detail = client.get(f"/api/monitor/runs/{run_id}")
    candidates = client.get(f"/api/monitor/runs/{run_id}/candidates")
    events = client.get(f"/api/monitor/runs/{run_id}/events")
    pushes = client.get("/api/pushes")
    quality = client.get("/api/eval/summary")

    assert run_detail.status_code == 200
    assert candidates.status_code == 200
    assert events.status_code == 200
    assert pushes.status_code == 200
    assert quality.status_code == 200
    assert run_detail.json()["run_id"] == run_id
    assert isinstance(candidates.json()["items"], list)
    assert isinstance(events.json()["events"], list)
    assert "run_count" in quality.json()
```

- [ ] **Step 2: Run the PostgreSQL durability tests to verify the current gaps**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py -q -k "phase_a_entities or persisted_phase_a_entities"
```

Expected: FAIL because the current endpoints and repository coverage do not yet prove the full durable-store contract as one locked Phase A requirement.

- [ ] **Step 3: Implement the minimal repository and API tightening**

Update `backend/app/storage/models.py` only if a required persisted field is missing; otherwise leave the schema stable. The main implementation work belongs in repository and API read paths.

Key implementation shape in `backend/app/storage/repository.py`:

```python
class SqlAlchemyMonitorRunRepository:
    def list_push_records(
        self,
        *,
        topic_id: str | None = None,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        statement = select(PushRecord)
        if topic_id is not None:
            statement = statement.where(PushRecord.topic_id == topic_id)
        if run_id is not None:
            statement = statement.where(PushRecord.run_id == run_id)
        records = self.session.scalars(
            statement.order_by(PushRecord.created_at.desc(), PushRecord.push_id.desc())
        ).all()
        return [self._serialize_push_record(record) for record in records]

    def get_eval_summary(self) -> dict[str, Any] | None:
        results = self.session.scalars(
            select(EvalResult).order_by(EvalResult.created_at.desc(), EvalResult.eval_id.desc())
        ).all()
        if not results:
            return None
        run_count = len(results)
        latest = results[0]
        return {
            "run_count": run_count,
            "total_push_count": sum(result.push_count for result in results),
            "total_duplicate_push_count": sum(result.duplicate_push_count for result in results),
            "total_raw_summary_count": sum(result.raw_summary_count for result in results),
            "total_browser_fallback_count": sum(result.browser_fallback_count for result in results),
            "total_provider_fallback_count": sum(result.provider_fallback_count for result in results),
            "avg_tool_success_rate": round(
                sum(result.tool_success_rate for result in results) / run_count,
                2,
            ),
            "avg_fetch_success_rate": round(
                sum(result.fetch_success_rate for result in results) / run_count,
                2,
            ),
            "avg_trace_completeness": round(
                sum(result.trace_completeness for result in results) / run_count,
                2,
            ),
            "latest_eval": self._serialize_eval_result(latest),
        }
```

Make sure the API handlers in `backend/app/api/candidates.py`, `backend/app/api/events.py`, `backend/app/api/pushes.py`, and `backend/app/api/eval.py` read persisted repository data rather than accidental snapshot-only data.

- [ ] **Step 4: Re-run the PostgreSQL durability tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py -q -k "phase_a_entities or persisted_phase_a_entities"
```

Expected: PASS.

- [ ] **Step 5: Update the backend README to state the durable-truth contract explicitly**

Update `backend/README.md` so it clearly states:

```markdown
- PostgreSQL is the durable source of truth for topics, monitor runs,
  candidates, extracted items, decisions, push records, run events, and eval
  results.
- Redis and Redis Stream do not replace PostgreSQL business facts.
- Elasticsearch/OpenSearch is a derived retrieval projection only.
```

- [ ] **Step 6: Run focused regression tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py tests/test_monitor_run_flow.py tests/test_topics_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py backend/app/storage/models.py backend/app/storage/repository.py backend/app/api/candidates.py backend/app/api/events.py backend/app/api/pushes.py backend/app/api/eval.py backend/README.md
git commit -m "feat: tighten postgres durable truth contract"
```

### Task 2: Harden Redis Coordination Responsibilities

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/tests/test_monitor_run_flow.py`
- Modify: `backend/app/storage/redis_store.py`
- Modify: `backend/app/scheduler/worker.py`
- Modify: `backend/app/api/monitor.py`
- Modify: `backend/README.md`

- [ ] **Step 1: Write the failing Redis coordination tests**

Add the following tests to `backend/tests/test_tools_and_eval.py`:

```python
def test_build_redis_client_uses_runtime_settings_url() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/5",
    )

    client = build_redis_client(settings)

    assert client.connection_pool.connection_kwargs["db"] == 5


def test_build_run_queue_falls_back_to_memory_when_redis_ping_fails(monkeypatch) -> None:
    class FailingRedis:
        def ping(self) -> None:
            raise RedisError("redis unavailable")

    monkeypatch.setattr(
        "app.scheduler.worker.build_redis_client",
        lambda settings=None: FailingRedis(),
    )

    queue = build_run_queue(
        Settings(
            database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
            redis_url="redis://localhost:6379/0",
        )
    )

    assert isinstance(queue, InMemoryRunQueue)
```

Add the following test to `backend/tests/test_monitor_run_flow.py`:

```python
def test_worker_persists_governance_failure_when_active_run_guard_uses_redis_queue() -> None:
    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()
    topic = topic_repository.create_topic(
        TopicCreateData(
            name="AI Agent",
            description="Track enterprise AI agent launches.",
            seed_keywords=("OpenAI", "LangGraph"),
            trusted_sources=("example.com",),
            exclude_keywords=("rumor",),
            push_threshold=0.72,
            cooldown_hours=24,
            enabled=True,
            schedule_cron="0 */6 * * *",
        )
    )
    active_run = MonitorRunRecord(
        run_id="run_active_guard",
        topic_id=topic.topic_id,
        status="running",
        state_snapshot={
            "run_id": "run_active_guard",
            "topic_id": topic.topic_id,
            "trigger": "scheduler",
            "status": "running",
        },
        error_summary=None,
        started_at=datetime(2026, 6, 24, 9, 0, tzinfo=UTC),
        finished_at=None,
        created_at=datetime(2026, 6, 24, 9, 0, tzinfo=UTC),
    )
    run_repository.monitor_runs[active_run.run_id] = active_run
    queue = InMemoryRunQueue()
    queue.enqueue(RunQueueMessage(topic_id=topic.topic_id, trigger="scheduler"))

    worker = MonitorWorkerService(
        topic_repository=topic_repository,
        run_repository=run_repository,
        llm=MockLLM(),
        queue=queue,
    )

    result = worker.process_next()

    assert result is not None
    assert result["status"] == "skipped_active_run"
    events = run_repository.list_run_events(active_run.run_id)
    assert events[0]["event_type"] == "governance_skipped"
    assert events[0]["payload"]["active_run_id"] == "run_active_guard"
```

- [ ] **Step 2: Run the Redis coordination tests to verify the current baseline**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py tests/test_monitor_run_flow.py -q -k "redis_client_uses_runtime_settings_url or falls_back_to_memory_when_redis_ping_fails or active_run_guard_uses_redis_queue"
```

Expected: PASS or partial PASS. If all pass immediately, treat that as proof that Redis coordination is already partially real and continue to Step 3 to strengthen explicit ownership and documentation.

- [ ] **Step 3: Make Redis-owned responsibilities explicit in code**

In `backend/app/storage/redis_store.py`, keep the builder focused:

```python
def build_redis_client(settings: Settings | None = None) -> Redis:
    resolved_settings = settings or get_settings()
    return Redis.from_url(
        resolved_settings.redis_url,
        decode_responses=True,
    )
```

In `backend/app/scheduler/worker.py`, make sure Redis-backed coordination is treated as:

- queue transport and short-lived coordination
- not the source of truth for run results
- visible fallback when Redis is unavailable

If needed, add explicit helper comments and event payload fields rather than changing the public API shape.

- [ ] **Step 4: Update README to define the Redis boundary**

Update `backend/README.md` so it clearly states:

```markdown
- Redis owns short-lived coordination such as queue transport, active-run
  protection, and transient execution state.
- If Redis is unavailable, the runtime may degrade to in-memory coordination,
  but PostgreSQL business facts remain durable and authoritative.
```

- [ ] **Step 5: Run focused regression tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py tests/test_monitor_run_flow.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py backend/app/storage/redis_store.py backend/app/scheduler/worker.py backend/app/api/monitor.py backend/README.md
git commit -m "feat: define redis coordination responsibilities"
```

### Task 3: Make APScheduler Runtime Ownership Explicit

**Files:**
- Modify: `backend/tests/test_topics_api.py`
- Modify: `backend/tests/test_monitor_run_flow.py`
- Modify: `backend/app/scheduler/jobs.py`
- Modify: `backend/app/main.py`
- Modify: `backend/README.md`

- [ ] **Step 1: Write the failing APScheduler lifecycle tests**

Add the following tests to `backend/tests/test_topics_api.py`:

```python
def test_register_topic_removes_existing_job_when_schedule_is_disabled() -> None:
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)
    try:
        queue = InMemoryRunQueue()
        service = TopicSchedulerService(scheduler=scheduler, queue=queue)
        service.register_topic(
            topic_id="topic_001",
            schedule_cron="0 */6 * * *",
            enabled=True,
        )
        assert scheduler.get_job("topic:topic_001") is not None

        service.register_topic(
            topic_id="topic_001",
            schedule_cron=None,
            enabled=False,
        )

        assert scheduler.get_job("topic:topic_001") is None
    finally:
        scheduler.shutdown(wait=False)


def test_rehydrate_topics_registers_only_enabled_topics_with_cron() -> None:
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)
    try:
        queue = InMemoryRunQueue()
        service = TopicSchedulerService(scheduler=scheduler, queue=queue)
        topics = [
            type("TopicLike", (), {
                "topic_id": "topic_enabled",
                "schedule_cron": "0 */6 * * *",
                "enabled": True,
            })(),
            type("TopicLike", (), {
                "topic_id": "topic_disabled",
                "schedule_cron": "0 */6 * * *",
                "enabled": False,
            })(),
            type("TopicLike", (), {
                "topic_id": "topic_missing_cron",
                "schedule_cron": None,
                "enabled": True,
            })(),
        ]

        service.rehydrate_topics(topics)

        assert scheduler.get_job("topic:topic_enabled") is not None
        assert scheduler.get_job("topic:topic_disabled") is None
        assert scheduler.get_job("topic:topic_missing_cron") is None
    finally:
        scheduler.shutdown(wait=False)
```

Add the following test to `backend/tests/test_monitor_run_flow.py`:

```python
def test_scheduler_job_enqueues_message_with_scheduler_trigger() -> None:
    queue = InMemoryRunQueue()
    result = enqueue_topic_run("topic_001", queue=queue, trigger="scheduler")
    message = queue.dequeue()

    assert result["status"] == "queued"
    assert message is not None
    assert message.topic_id == "topic_001"
    assert message.trigger == "scheduler"
```

- [ ] **Step 2: Run the APScheduler tests to verify current behavior**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_topics_api.py tests/test_monitor_run_flow.py -q -k "removes_existing_job_when_schedule_is_disabled or rehydrate_topics_registers_only_enabled_topics_with_cron or scheduler_job_enqueues_message_with_scheduler_trigger"
```

Expected: PASS or partial PASS. If all pass, continue to Step 3 so the runtime ownership is still made explicit in startup and docs.

- [ ] **Step 3: Tighten scheduler lifecycle ownership**

In `backend/app/scheduler/jobs.py`, keep registration rules explicit:

```python
def register_topic(self, *, topic_id: str, schedule_cron: str | None, enabled: bool) -> None:
    job_id = self._job_id(topic_id)
    existing = self.scheduler.get_job(job_id)
    if existing is not None:
        self.scheduler.remove_job(job_id)

    if not enabled or not schedule_cron:
        return

    self.scheduler.add_job(
        enqueue_topic_run,
        trigger=CronTrigger.from_crontab(schedule_cron),
        id=job_id,
        kwargs={
            "topic_id": topic_id,
            "queue": self.queue,
            "trigger": "scheduler",
        },
        replace_existing=True,
    )
```

In `backend/app/main.py`, make startup ownership explicit:

- build scheduler once in lifespan
- rehydrate jobs before scheduler start
- start scheduler once
- always shut it down in lifespan cleanup

- [ ] **Step 4: Update README for APScheduler ownership**

Update `backend/README.md` with wording like:

```markdown
- APScheduler owns topic-bound cron registration and trigger production.
- APScheduler does not execute the heavy monitor flow directly; it enqueues work
  for worker consumption.
```

- [ ] **Step 5: Run focused regression tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_topics_api.py tests/test_monitor_run_flow.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_topics_api.py backend/tests/test_monitor_run_flow.py backend/app/scheduler/jobs.py backend/app/main.py backend/README.md
git commit -m "feat: make scheduler runtime ownership explicit"
```

### Task 4: Correct Redis Stream Consumer-Group Semantics

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/tests/test_monitor_run_flow.py`
- Modify: `backend/app/scheduler/worker.py`
- Modify: `backend/README.md`

- [ ] **Step 1: Write the failing Redis Stream ack/retry tests**

Add the following tests to `backend/tests/test_tools_and_eval.py`:

```python
def test_redis_stream_queue_acknowledges_only_after_explicit_success() -> None:
    acknowledgements: list[tuple[str, str, str]] = []

    class FakeRedis:
        def xgroup_create(self, name: str, groupname: str, id: str, mkstream: bool) -> None:
            return None

        def xadd(self, stream_key: str, payload: dict[str, str]) -> str:
            return "1700000000000-0"

        def xreadgroup(
            self,
            *,
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
                            b"1700000000000-0",
                            {
                                b"topic_id": b"topic_001",
                                b"trigger": b"scheduler",
                                b"enqueued_at": b"2026-06-24T10:00:00Z",
                            },
                        )
                    ],
                )
            ]

        def xack(self, stream_name: str, group_name: str, message_id: bytes) -> int:
            acknowledgements.append((stream_name, group_name, message_id.decode("utf-8")))
            return 1

    queue = RedisStreamRunQueue(FakeRedis())

    delivery = queue.dequeue()
    assert delivery is not None
    assert delivery.topic_id == "topic_001"
    assert acknowledgements == []

    queue.acknowledge(delivery)

    assert acknowledgements == [
        ("industry_news_agent:run_stream", "monitor-workers", "1700000000000-0")
    ]


def test_redis_stream_queue_requeues_failed_delivery() -> None:
    requeues: list[dict[str, str]] = []

    class FakeRedis:
        def xgroup_create(self, name: str, groupname: str, id: str, mkstream: bool) -> None:
            return None

        def xadd(self, stream_key: str, payload: dict[str, str]) -> str:
            requeues.append(payload)
            return "1700000000001-0"

        def xreadgroup(
            self,
            *,
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
                            b"1700000000000-0",
                            {
                                b"topic_id": b"topic_001",
                                b"trigger": b"scheduler",
                                b"enqueued_at": b"2026-06-24T10:00:00Z",
                            },
                        )
                    ],
                )
            ]

        def xack(self, stream_name: str, group_name: str, message_id: bytes) -> int:
            return 1

    queue = RedisStreamRunQueue(FakeRedis())
    delivery = queue.dequeue()
    assert delivery is not None

    queue.requeue(delivery, reason="worker_failed")

    assert requeues[0]["topic_id"] == "topic_001"
    assert requeues[0]["trigger"] == "scheduler"
    assert requeues[0]["retry_reason"] == "worker_failed"
```

Add this test to `backend/tests/test_monitor_run_flow.py`:

```python
def test_worker_acknowledges_queue_message_only_after_successful_completion() -> None:
    acknowledgements: list[str] = []

    class RecordingQueue(InMemoryRunQueue):
        def __init__(self) -> None:
            super().__init__()
            self.last_delivery: RunQueueMessage | None = None

        def dequeue(self) -> RunQueueMessage | None:
            self.last_delivery = super().dequeue()
            return self.last_delivery

        def acknowledge(self, delivery: RunQueueMessage) -> None:
            acknowledgements.append(delivery.topic_id)

    topic_repository = InMemoryTopicRepository()
    run_repository = InMemoryMonitorRunRepository()
    topic = topic_repository.create_topic(
        TopicCreateData(
            name="AI Agent",
            description="Track enterprise AI agent launches.",
            seed_keywords=("OpenAI", "LangGraph"),
            trusted_sources=("example.com",),
            exclude_keywords=("rumor",),
            push_threshold=0.72,
            cooldown_hours=24,
            enabled=True,
            schedule_cron="0 */6 * * *",
        )
    )
    queue = RecordingQueue()
    queue.enqueue(RunQueueMessage(topic_id=topic.topic_id, trigger="scheduler"))

    worker = MonitorWorkerService(
        topic_repository=topic_repository,
        run_repository=run_repository,
        llm=MockLLM(),
        queue=queue,
    )

    result = worker.process_next()

    assert result is not None
    assert result["status"] == "completed"
    assert acknowledgements == [topic.topic_id]
```

- [ ] **Step 2: Run the Redis Stream semantics tests to verify failure**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py tests/test_monitor_run_flow.py -q -k "acknowledges_only_after_explicit_success or requeues_failed_delivery or acknowledges_queue_message_only_after_successful_completion"
```

Expected: FAIL because the current `RedisStreamRunQueue.dequeue()` acks immediately and the queue protocol does not yet expose explicit post-processing acknowledgement hooks.

- [ ] **Step 3: Introduce explicit queue delivery acknowledgment semantics**

Update `backend/app/scheduler/worker.py` to change the queue contract:

```python
class RunQueueProtocol(Protocol):
    def enqueue(self, message: RunQueueMessage) -> dict[str, Any]: ...
    def dequeue(self) -> RunQueueMessage | None: ...
    def acknowledge(self, delivery: RunQueueMessage) -> None: ...
    def requeue(self, delivery: RunQueueMessage, *, reason: str) -> None: ...
```

Extend `RunQueueMessage` with delivery metadata:

```python
@dataclass(frozen=True, slots=True)
class RunQueueMessage:
    topic_id: str
    trigger: str
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    queue_message_id: str | None = None
    queue_stream: str | None = None
```

Adjust `InMemoryRunQueue`:

```python
class InMemoryRunQueue:
    def acknowledge(self, delivery: RunQueueMessage) -> None:
        return None

    def requeue(self, delivery: RunQueueMessage, *, reason: str) -> None:
        self.enqueue(
            RunQueueMessage(
                topic_id=delivery.topic_id,
                trigger=delivery.trigger,
                enqueued_at=datetime.now(UTC),
            )
        )
```

Adjust `RedisStreamRunQueue.dequeue()` so it returns the delivery metadata without acking:

```python
return RunQueueMessage(
    topic_id=str(payload["topic_id"]),
    trigger=str(payload["trigger"]),
    enqueued_at=datetime.fromisoformat(str(payload["enqueued_at"]).replace("Z", "+00:00")),
    queue_message_id=self._to_text(message_id),
    queue_stream=self._to_text(stream_name),
)
```

Add explicit acknowledgement:

```python
def acknowledge(self, delivery: RunQueueMessage) -> None:
    if not delivery.queue_message_id or not delivery.queue_stream:
        return
    self.redis_client.xack(
        delivery.queue_stream,
        self.group_name,
        delivery.queue_message_id,
    )
```

Add explicit requeue:

```python
def requeue(self, delivery: RunQueueMessage, *, reason: str) -> None:
    self.enqueue(
        RunQueueMessage(
            topic_id=delivery.topic_id,
            trigger=delivery.trigger,
            enqueued_at=datetime.now(UTC),
        )
    )
    self.acknowledge(delivery)
```

Update `MonitorWorkerService.process_next()` so it:

- calls `queue.acknowledge(message)` only after a successful run or an intentional active-run skip
- calls `queue.requeue(message, reason="worker_retry")` before retrying if the queue type supports explicit requeue
- calls `queue.acknowledge(message)` after a final failed run is persisted

- [ ] **Step 4: Re-run the Redis Stream semantics tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py tests/test_monitor_run_flow.py -q -k "acknowledges_only_after_explicit_success or requeues_failed_delivery or acknowledges_queue_message_only_after_successful_completion"
```

Expected: PASS.

- [ ] **Step 5: Update README to describe real stream semantics**

Update `backend/README.md` with wording like:

```markdown
- Redis Stream consumer groups own queued delivery transport.
- A delivery is acknowledged only after the worker has either completed the run
  or intentionally closed it.
- Retry behavior is explicit rather than implied by immediate dequeue ack.
```

- [ ] **Step 6: Run focused regression tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py tests/test_monitor_run_flow.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py backend/app/scheduler/worker.py backend/README.md
git commit -m "feat: harden redis stream delivery semantics"
```

### Task 5: Promote Elasticsearch Projection Into A Real Queryable Retrieval Layer

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/tests/test_monitor_run_flow.py`
- Modify: `backend/app/search/history_index.py`
- Modify: `backend/app/agent/nodes.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/README.md`

- [ ] **Step 1: Write the failing Elasticsearch query-path tests**

Add the following tests to `backend/tests/test_tools_and_eval.py`:

```python
def test_opensearch_history_index_can_search_candidate_documents() -> None:
    from app.search.history_index import OpenSearchHistoryIndex

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self.payload

    class FakeClient:
        def __init__(self) -> None:
            self.put_requests: list[dict[str, object]] = []
            self.post_requests: list[dict[str, object]] = []

        def put(self, url: str, **kwargs: object) -> FakeResponse:
            self.put_requests.append({"url": url, **kwargs})
            return FakeResponse({"result": "created"})

        def post(self, url: str, **kwargs: object) -> FakeResponse:
            self.post_requests.append({"url": url, **kwargs})
            return FakeResponse(
                {
                    "hits": {
                        "hits": [
                            {
                                "_source": {
                                    "candidate_id": "cand_001",
                                    "title": "OpenAI agent update",
                                    "topic_id": "topic_ai",
                                }
                            }
                        ]
                    }
                }
            )

    client = FakeClient()
    index = OpenSearchHistoryIndex(
        base_url="http://localhost:9200",
        index_name="industry-news-candidates",
        http_client=client,
        timeout_seconds=3.0,
    )

    search_result = index.search_candidates("OpenAI agent", top_k=3)

    assert search_result["provider"] == "opensearch"
    assert search_result["query"] == "OpenAI agent"
    assert search_result["items"][0]["candidate_id"] == "cand_001"
    assert client.post_requests[0]["url"] == (
        "http://localhost:9200/industry-news-candidates/_search"
    )


def test_build_history_index_returns_noop_when_search_settings_are_incomplete() -> None:
    from app.search.history_index import NoopHistoryIndex, build_history_index

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        history_index_provider="opensearch",
        opensearch_base_url=None,
    )

    assert isinstance(build_history_index(settings=settings), NoopHistoryIndex)
```

Add the following test to `backend/tests/test_monitor_run_flow.py`:

```python
def test_supervisor_finalize_records_history_index_search_metadata() -> None:
    class RecordingIndex:
        def index_candidates(self, candidates: list[dict[str, object]]) -> dict[str, object]:
            return {"indexed_count": len(candidates), "provider": "opensearch"}

        def search_candidates(self, query: str, top_k: int = 5) -> dict[str, object]:
            return {
                "provider": "opensearch",
                "query": query,
                "items": [{"candidate_id": "cand_001", "title": "OpenAI agent update"}],
            }

    state = {
        "run_id": "run_index_search",
        "topic_id": "topic_ai",
        "topic": {"name": "AI Agent"},
        "candidate_items": [
            {
                "candidate_id": "cand_001",
                "run_id": "run_index_search",
                "topic_id": "topic_ai",
                "title": "OpenAI agent update",
                "url": "https://example.com/agent",
            }
        ],
        "events": [],
        "errors": [],
        "tool_results": [],
        "status": "running",
    }

    result = supervisor_finalize_node(
        state,
        history_index=RecordingIndex(),
    )

    assert result["history_index_result"]["indexed_count"] == 1
```

- [ ] **Step 2: Run the Elasticsearch query-path tests to verify failure**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py tests/test_monitor_run_flow.py -q -k "can_search_candidate_documents or history_index_search_metadata"
```

Expected: FAIL because the current history index supports indexing only and does not yet expose a real query contract.

- [ ] **Step 3: Extend the history index contract with query support**

Update `backend/app/search/history_index.py`:

```python
class HistoryIndexProtocol(Protocol):
    def index_candidates(self, candidates: list[dict[str, Any]]) -> dict[str, Any]: ...
    def search_candidates(self, query: str, top_k: int = 5) -> dict[str, Any]: ...


class NoopHistoryIndex:
    def index_candidates(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        return {"indexed_count": 0, "provider": "none"}

    def search_candidates(self, query: str, top_k: int = 5) -> dict[str, Any]:
        return {"provider": "none", "query": query, "items": []}
```

Implement real query support:

```python
def search_candidates(self, query: str, top_k: int = 5) -> dict[str, Any]:
    client = self.http_client or httpx
    response = client.post(
        f"{self.base_url}/{self.index_name}/_search",
        json={
            "size": top_k,
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "raw_summary^2", "content", "decision_reason"],
                }
            },
        },
        timeout=self.timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    hits = payload.get("hits", {}).get("hits", [])
    return {
        "provider": "opensearch",
        "query": query,
        "items": [dict(hit.get("_source", {})) for hit in hits],
    }
```

Only add query use to the run state or events if it stays truthful and does not change the public monitor API shape.

- [ ] **Step 4: Re-run the Elasticsearch query-path tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py tests/test_monitor_run_flow.py -q -k "can_search_candidate_documents or history_index_search_metadata"
```

Expected: PASS.

- [ ] **Step 5: Update README to describe Elasticsearch as a real derived retrieval layer**

Update `backend/README.md` so it says:

```markdown
- OpenSearch/Elasticsearch is a derived candidate-history retrieval layer.
- It supports projection and query, but PostgreSQL remains the durable source of
  truth.
```

- [ ] **Step 6: Run focused regression tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py tests/test_monitor_run_flow.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py backend/app/search/history_index.py backend/app/agent/nodes.py backend/app/core/config.py backend/README.md
git commit -m "feat: add queryable history index contract"
```

### Task 6: Foundation Verification And Delivery Evidence

**Files:**
- Modify: `backend/README.md`
- Modify: `docker-compose.yml`
- Modify: any touched backend files required for integration fixes

- [ ] **Step 1: Run the backend foundation suite**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py tests/test_monitor_run_flow.py tests/test_topics_api.py tests/test_health_api.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the full backend suite**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest -q
```

Expected: PASS.

- [ ] **Step 3: Verify repo hygiene**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp
git diff --check
git status --short
```

Expected: no whitespace errors and only intended Phase A foundation changes remain.

- [ ] **Step 4: Verify local demonstration stack configuration**

Inspect `docker-compose.yml` and `backend/README.md` so they stay consistent with:

```yaml
services:
  backend:
    environment:
      DATABASE_URL: postgresql+psycopg://news_agent:news_agent@postgres:5432/news_agent
      REDIS_URL: redis://redis:6379/0
```

If the runtime contract changed during Tasks 1-5, update the compose file or README so the documented local stack still reflects the actual required infrastructure.

- [ ] **Step 5: Commit the foundation milestone**

```bash
git add backend docker-compose.yml
git commit -m "feat: complete phase a foundation alignment"
```

## Self-Review

### Spec Coverage

- `PostgreSQL`: covered by Task 1
- `Redis`: covered by Task 2
- `APScheduler`: covered by Task 3
- `Redis Stream`: covered by Task 4
- `Elasticsearch`: covered by Task 5
- foundation verification and evidence closure: covered by Task 6

No Phase A foundation gap remains in this plan.

### Placeholder Scan

- No `TBD`, `TODO`, or deferred filler text is used as a task step.
- Every task includes explicit files, test direction, commands, and commit points.

### Type Consistency

- Queue contract additions use `acknowledge` and `requeue` consistently.
- Elasticsearch/OpenSearch work uses the existing `history_index` naming to stay aligned with the current codebase.
- Persistence data classes reuse the existing repository dataclass names instead of inventing new ones.
