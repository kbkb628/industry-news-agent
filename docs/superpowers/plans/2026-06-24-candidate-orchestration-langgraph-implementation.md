# Candidate Orchestration LangGraph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the monitor pipeline from stage-only execution into real candidate-level orchestration with bounded same-stage concurrency, Redis-owned runtime coordination semantics, and PostgreSQL-backed durable task evidence.

**Architecture:** Keep LangGraph as the top-level run skeleton and insert a candidate orchestrator after retrieval rather than replacing the graph with a separate task engine. Persist durable task ledger facts in PostgreSQL, keep short-lived runtime coordination in run state and Redis-oriented semantics, and reuse the existing extraction/evaluation modules as task workers so the implementation stays aligned with the resume and `DEVELOPMENT_GUIDE.md`.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, SQLAlchemy, PostgreSQL, Redis, pytest, concurrent.futures

---

### Task 1: Add Candidate Task Contracts And Run-State Fields

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/app/agent/contracts.py`
- Modify: `backend/app/agent/state.py`
- Modify: `backend/app/api/monitor.py`

- [ ] **Step 1: Write the failing contract tests**

Add the following tests to `backend/tests/test_tools_and_eval.py`:

```python
def test_build_empty_candidate_task_output_contract() -> None:
    from app.agent.contracts import build_empty_candidate_task_output

    output = build_empty_candidate_task_output()

    assert output == {
        "tasks": [],
        "runtime": {
            "ready_count": 0,
            "in_progress_count": 0,
            "completed_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "stage_slots": {
                "fetch": {"limit": 0, "in_progress": 0},
                "extract": {"limit": 0, "in_progress": 0},
                "evaluate": {"limit": 0, "in_progress": 0},
            },
        },
        "summary": {
            "task_count": 0,
            "completed_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "fetch_completed_count": 0,
            "extract_completed_count": 0,
            "evaluate_completed_count": 0,
        },
    }


def test_monitor_state_can_hold_candidate_orchestration_fields() -> None:
    from app.agent.contracts import build_empty_candidate_task_output

    orchestration = build_empty_candidate_task_output()
    state = {
        "candidate_task_plan": orchestration["tasks"],
        "candidate_task_runtime": orchestration["runtime"],
        "candidate_task_summary": orchestration["summary"],
    }

    assert state["candidate_task_plan"] == []
    assert state["candidate_task_runtime"]["stage_slots"]["fetch"]["limit"] == 0
    assert state["candidate_task_summary"]["task_count"] == 0
```

- [ ] **Step 2: Run the contract tests to verify failure**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py -q -k "candidate_task_output_contract or candidate_orchestration_fields"
```

Expected: FAIL because the candidate orchestration contract does not exist yet.

- [ ] **Step 3: Add the minimal candidate task contract**

Update `backend/app/agent/contracts.py` to add TypedDicts and an empty builder:

```python
class CandidateTaskRecord(TypedDict, total=False):
    task_id: str
    run_id: str
    candidate_id: str
    stage: str
    status: str
    attempt: int
    max_attempts: int
    depends_on_task_ids: list[str]
    input_ref: dict[str, Any]
    output_ref: dict[str, Any]
    error_code: str | None
    error_message: str | None
    started_at: str | None
    finished_at: str | None


class CandidateTaskRuntime(TypedDict, total=False):
    ready_count: int
    in_progress_count: int
    completed_count: int
    failed_count: int
    skipped_count: int
    stage_slots: dict[str, dict[str, int]]


class CandidateTaskSummary(TypedDict, total=False):
    task_count: int
    completed_count: int
    failed_count: int
    skipped_count: int
    fetch_completed_count: int
    extract_completed_count: int
    evaluate_completed_count: int


def build_empty_candidate_task_output() -> dict[str, Any]:
    return {
        "tasks": [],
        "runtime": {
            "ready_count": 0,
            "in_progress_count": 0,
            "completed_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "stage_slots": {
                "fetch": {"limit": 0, "in_progress": 0},
                "extract": {"limit": 0, "in_progress": 0},
                "evaluate": {"limit": 0, "in_progress": 0},
            },
        },
        "summary": {
            "task_count": 0,
            "completed_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "fetch_completed_count": 0,
            "extract_completed_count": 0,
            "evaluate_completed_count": 0,
        },
    }
```

Update `backend/app/agent/state.py` to add:

```python
    candidate_task_plan: list[dict[str, Any]]
    candidate_task_runtime: dict[str, Any]
    candidate_task_summary: dict[str, Any]
```

Update `backend/app/api/monitor.py` `_build_initial_state()` to seed:

```python
    orchestration = build_empty_candidate_task_output()
    return {
        ...
        "candidate_task_plan": list(orchestration["tasks"]),
        "candidate_task_runtime": dict(orchestration["runtime"]),
        "candidate_task_summary": dict(orchestration["summary"]),
        ...
    }
```

- [ ] **Step 4: Re-run the contract tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py -q -k "candidate_task_output_contract or candidate_orchestration_fields"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_tools_and_eval.py backend/app/agent/contracts.py backend/app/agent/state.py backend/app/api/monitor.py
git commit -m "feat: add candidate orchestration state contract"
```

### Task 2: Add PostgreSQL Candidate Task Ledger Persistence

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/app/storage/models.py`
- Modify: `backend/app/storage/repository.py`

- [ ] **Step 1: Write the failing task ledger persistence tests**

Add the following tests to `backend/tests/test_tools_and_eval.py`:

```python
def test_sqlalchemy_repository_persists_candidate_task_ledger(tmp_path) -> None:
    from app.core.config import Settings
    from app.storage.database import Base, build_engine, build_session_factory
    from app.storage.repository import (
        CandidateTaskRecordCreateData,
        SqlAlchemyMonitorRunRepository,
    )

    database_url = f"sqlite+pysqlite:///{tmp_path / 'candidate_task_ledger.db'}"
    settings = Settings(
        database_url=database_url,
        redis_url="redis://localhost:6379/0",
    )
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    session = build_session_factory(engine)()
    try:
        repository = SqlAlchemyMonitorRunRepository(session=session)

        created = repository.create_candidate_task_records(
            (
                CandidateTaskRecordCreateData(
                    task_id="task_fetch_cand_001",
                    run_id="run_candidate_tasks",
                    candidate_id="cand_001",
                    stage="fetch",
                    status="completed",
                    attempt=1,
                    max_attempts=2,
                    depends_on_task_ids=(),
                    input_ref={"candidate_id": "cand_001"},
                    output_ref={"fetched_candidate_id": "cand_001"},
                    error_code=None,
                    error_message=None,
                    started_at=datetime(2026, 6, 24, 11, 0, tzinfo=UTC),
                    finished_at=datetime(2026, 6, 24, 11, 1, tzinfo=UTC),
                ),
            )
        )

        assert created[0]["task_id"] == "task_fetch_cand_001"
        assert created[0]["stage"] == "fetch"
        assert created[0]["status"] == "completed"
        assert created[0]["output_ref"]["fetched_candidate_id"] == "cand_001"
        assert repository.list_candidate_task_records("run_candidate_tasks")[0]["task_id"] == "task_fetch_cand_001"
    finally:
        session.close()
        engine.dispose()


def test_sqlalchemy_repository_lists_candidate_task_records_by_candidate(tmp_path) -> None:
    from app.core.config import Settings
    from app.storage.database import Base, build_engine, build_session_factory
    from app.storage.repository import (
        CandidateTaskRecordCreateData,
        SqlAlchemyMonitorRunRepository,
    )

    database_url = f"sqlite+pysqlite:///{tmp_path / 'candidate_task_lookup.db'}"
    settings = Settings(
        database_url=database_url,
        redis_url="redis://localhost:6379/0",
    )
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    session = build_session_factory(engine)()
    try:
        repository = SqlAlchemyMonitorRunRepository(session=session)
        repository.create_candidate_task_records(
            (
                CandidateTaskRecordCreateData(
                    task_id="task_fetch_cand_001",
                    run_id="run_candidate_tasks",
                    candidate_id="cand_001",
                    stage="fetch",
                    status="completed",
                    attempt=1,
                    max_attempts=2,
                    depends_on_task_ids=(),
                    input_ref={"candidate_id": "cand_001"},
                    output_ref={},
                    error_code=None,
                    error_message=None,
                    started_at=None,
                    finished_at=None,
                ),
                CandidateTaskRecordCreateData(
                    task_id="task_extract_cand_002",
                    run_id="run_candidate_tasks",
                    candidate_id="cand_002",
                    stage="extract",
                    status="failed",
                    attempt=2,
                    max_attempts=2,
                    depends_on_task_ids=("task_fetch_cand_002",),
                    input_ref={"candidate_id": "cand_002"},
                    output_ref={},
                    error_code="content_error",
                    error_message="empty content",
                    started_at=None,
                    finished_at=None,
                ),
            )
        )

        filtered = repository.list_candidate_task_records(
            "run_candidate_tasks",
            candidate_id="cand_002",
        )

        assert len(filtered) == 1
        assert filtered[0]["task_id"] == "task_extract_cand_002"
        assert filtered[0]["error_code"] == "content_error"
    finally:
        session.close()
        engine.dispose()
```

- [ ] **Step 2: Run the task ledger persistence tests to verify failure**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py -q -k "candidate_task_ledger or candidate_task_records_by_candidate"
```

Expected: FAIL because the task ledger model and repository methods do not exist yet.

- [ ] **Step 3: Add the task ledger model and repository methods**

Update `backend/app/storage/models.py` to add a new SQLAlchemy model:

```python
class CandidateTaskRecord(Base):
    __tablename__ = "candidate_task_records"

    task_id = mapped_column(String(128), primary_key=True)
    run_id = mapped_column(String(64), index=True, nullable=False)
    candidate_id = mapped_column(String(64), index=True, nullable=False)
    stage = mapped_column(String(32), nullable=False)
    status = mapped_column(String(32), nullable=False)
    attempt = mapped_column(Integer, nullable=False, default=1)
    max_attempts = mapped_column(Integer, nullable=False, default=1)
    depends_on_task_ids = mapped_column(JSON, nullable=False, default=list)
    input_ref = mapped_column(JSON, nullable=False, default=dict)
    output_ref = mapped_column(JSON, nullable=False, default=dict)
    error_code = mapped_column(String(64), nullable=True)
    error_message = mapped_column(Text, nullable=True)
    started_at = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at = mapped_column(DateTime(timezone=True), nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
```

Update `backend/app/storage/repository.py` to add:

```python
@dataclass(frozen=True, slots=True)
class CandidateTaskRecordCreateData:
    task_id: str
    run_id: str
    candidate_id: str
    stage: str
    status: str
    attempt: int
    max_attempts: int
    depends_on_task_ids: tuple[str, ...]
    input_ref: dict[str, Any]
    output_ref: dict[str, Any]
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
```

Extend `MonitorRunRepositoryProtocol` and implementations with:

```python
    def create_candidate_task_records(
        self,
        payloads: tuple[CandidateTaskRecordCreateData, ...],
    ) -> list[dict[str, Any]]: ...

    def list_candidate_task_records(
        self,
        run_id: str,
        *,
        candidate_id: str | None = None,
    ) -> list[dict[str, Any]]: ...
```

Implement the SQLAlchemy methods with:

```python
    def create_candidate_task_records(
        self,
        payloads: tuple[CandidateTaskRecordCreateData, ...],
    ) -> list[dict[str, Any]]:
        models: list[CandidateTaskRecord] = []
        for payload in payloads:
            model = CandidateTaskRecord(
                task_id=payload.task_id,
                run_id=payload.run_id,
                candidate_id=payload.candidate_id,
                stage=payload.stage,
                status=payload.status,
                attempt=payload.attempt,
                max_attempts=payload.max_attempts,
                depends_on_task_ids=list(payload.depends_on_task_ids),
                input_ref=dict(payload.input_ref),
                output_ref=dict(payload.output_ref),
                error_code=payload.error_code,
                error_message=payload.error_message,
                started_at=payload.started_at,
                finished_at=payload.finished_at,
            )
            self.session.add(model)
            models.append(model)

        self._commit()
        for model in models:
            self.session.refresh(model)
        return [self._serialize_candidate_task_record(model) for model in models]

    def list_candidate_task_records(
        self,
        run_id: str,
        *,
        candidate_id: str | None = None,
    ) -> list[dict[str, Any]]:
        statement = select(CandidateTaskRecord).where(
            CandidateTaskRecord.run_id == run_id
        )
        if candidate_id is not None:
            statement = statement.where(CandidateTaskRecord.candidate_id == candidate_id)
        models = self.session.scalars(
            statement.order_by(
                CandidateTaskRecord.created_at.asc(),
                CandidateTaskRecord.task_id.asc(),
            )
        ).all()
        return [self._serialize_candidate_task_record(model) for model in models]
```

- [ ] **Step 4: Re-run the task ledger persistence tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py -q -k "candidate_task_ledger or candidate_task_records_by_candidate"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_tools_and_eval.py backend/app/storage/models.py backend/app/storage/repository.py
git commit -m "feat: add candidate task ledger persistence"
```

### Task 3: Build Candidate Task Orchestrator Core

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Create: `backend/app/agent/candidate_orchestrator.py`
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Write the failing orchestrator unit tests**

Add the following tests to `backend/tests/test_tools_and_eval.py`:

```python
def test_candidate_orchestrator_creates_fetch_tasks_from_candidate_pool() -> None:
    from app.agent.candidate_orchestrator import CandidateTaskOrchestrator

    orchestrator = CandidateTaskOrchestrator()
    state = {
        "run_id": "run_orchestrator",
        "retrieval_output": {
            "candidate_pool": [
                {"candidate_id": "cand_001", "title": "AI Agent update"},
                {"candidate_id": "cand_002", "title": "MCP tool launch"},
            ]
        },
        "candidate_task_plan": [],
        "candidate_task_runtime": {},
        "candidate_task_summary": {},
    }

    result = orchestrator.build_initial_tasks(state)

    assert [task["task_id"] for task in result] == [
        "run_orchestrator:fetch:cand_001",
        "run_orchestrator:fetch:cand_002",
    ]
    assert all(task["stage"] == "fetch" for task in result)
    assert all(task["status"] == "ready" for task in result)


def test_candidate_orchestrator_creates_extract_task_after_fetch_completion() -> None:
    from app.agent.candidate_orchestrator import CandidateTaskOrchestrator

    orchestrator = CandidateTaskOrchestrator()
    task = {
        "task_id": "run_orchestrator:fetch:cand_001",
        "run_id": "run_orchestrator",
        "candidate_id": "cand_001",
        "stage": "fetch",
        "status": "completed",
        "attempt": 1,
        "max_attempts": 2,
        "depends_on_task_ids": [],
        "input_ref": {"candidate_id": "cand_001"},
        "output_ref": {"fetched_candidate_id": "cand_001"},
    }

    next_tasks = orchestrator.build_follow_up_tasks(task)

    assert next_tasks == [
        {
            "task_id": "run_orchestrator:extract:cand_001",
            "run_id": "run_orchestrator",
            "candidate_id": "cand_001",
            "stage": "extract",
            "status": "ready",
            "attempt": 1,
            "max_attempts": 2,
            "depends_on_task_ids": ["run_orchestrator:fetch:cand_001"],
            "input_ref": {"candidate_id": "cand_001"},
            "output_ref": {},
            "error_code": None,
            "error_message": None,
            "started_at": None,
            "finished_at": None,
        }
    ]


def test_candidate_orchestrator_runtime_summary_counts_statuses() -> None:
    from app.agent.candidate_orchestrator import CandidateTaskOrchestrator

    orchestrator = CandidateTaskOrchestrator(
        fetch_concurrency=2,
        extract_concurrency=1,
        evaluate_concurrency=1,
    )
    tasks = [
        {"stage": "fetch", "status": "ready"},
        {"stage": "fetch", "status": "in_progress"},
        {"stage": "extract", "status": "completed"},
        {"stage": "evaluate", "status": "failed"},
    ]

    runtime = orchestrator.build_runtime_view(tasks)
    summary = orchestrator.build_summary(tasks)

    assert runtime["ready_count"] == 1
    assert runtime["in_progress_count"] == 1
    assert runtime["stage_slots"]["fetch"] == {"limit": 2, "in_progress": 1}
    assert summary["task_count"] == 4
    assert summary["failed_count"] == 1
    assert summary["extract_completed_count"] == 1
```

- [ ] **Step 2: Run the orchestrator unit tests to verify failure**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py -q -k "orchestrator_creates_fetch_tasks or follow_up_tasks or runtime_summary_counts_statuses"
```

Expected: FAIL because the orchestrator module does not exist yet.

- [ ] **Step 3: Add the candidate orchestrator core**

Create `backend/app/agent/candidate_orchestrator.py` with:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class CandidateTaskOrchestrator:
    def __init__(
        self,
        *,
        fetch_concurrency: int = 2,
        extract_concurrency: int = 2,
        evaluate_concurrency: int = 2,
    ) -> None:
        self.fetch_concurrency = fetch_concurrency
        self.extract_concurrency = extract_concurrency
        self.evaluate_concurrency = evaluate_concurrency

    def build_initial_tasks(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        run_id = str(state["run_id"])
        candidate_pool = list(state.get("retrieval_output", {}).get("candidate_pool", []))
        tasks: list[dict[str, Any]] = []
        for candidate in candidate_pool:
            candidate_id = str(candidate["candidate_id"])
            tasks.append(
                {
                    "task_id": f"{run_id}:fetch:{candidate_id}",
                    "run_id": run_id,
                    "candidate_id": candidate_id,
                    "stage": "fetch",
                    "status": "ready",
                    "attempt": 1,
                    "max_attempts": 2,
                    "depends_on_task_ids": [],
                    "input_ref": {"candidate_id": candidate_id},
                    "output_ref": {},
                    "error_code": None,
                    "error_message": None,
                    "started_at": None,
                    "finished_at": None,
                }
            )
        return tasks

    def build_follow_up_tasks(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        if task.get("status") != "completed":
            return []

        run_id = str(task["run_id"])
        candidate_id = str(task["candidate_id"])
        stage = str(task["stage"])
        if stage == "fetch":
            next_stage = "extract"
        elif stage == "extract":
            next_stage = "evaluate"
        else:
            return []

        return [
            {
                "task_id": f"{run_id}:{next_stage}:{candidate_id}",
                "run_id": run_id,
                "candidate_id": candidate_id,
                "stage": next_stage,
                "status": "ready",
                "attempt": 1,
                "max_attempts": 2,
                "depends_on_task_ids": [str(task["task_id"])],
                "input_ref": {"candidate_id": candidate_id},
                "output_ref": {},
                "error_code": None,
                "error_message": None,
                "started_at": None,
                "finished_at": None,
            }
        ]

    def mark_task_completed(
        self,
        task: dict[str, Any],
        *,
        output_ref: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        completed = dict(task)
        completed["status"] = "completed"
        completed["output_ref"] = dict(output_ref or {})
        completed["finished_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return completed

    def build_runtime_view(self, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "ready_count": sum(1 for task in tasks if task.get("status") == "ready"),
            "in_progress_count": sum(
                1 for task in tasks if task.get("status") == "in_progress"
            ),
            "completed_count": sum(
                1 for task in tasks if task.get("status") == "completed"
            ),
            "failed_count": sum(1 for task in tasks if task.get("status") == "failed"),
            "skipped_count": sum(1 for task in tasks if task.get("status") == "skipped"),
            "stage_slots": {
                "fetch": {
                    "limit": self.fetch_concurrency,
                    "in_progress": sum(
                        1
                        for task in tasks
                        if task.get("stage") == "fetch"
                        and task.get("status") == "in_progress"
                    ),
                },
                "extract": {
                    "limit": self.extract_concurrency,
                    "in_progress": sum(
                        1
                        for task in tasks
                        if task.get("stage") == "extract"
                        and task.get("status") == "in_progress"
                    ),
                },
                "evaluate": {
                    "limit": self.evaluate_concurrency,
                    "in_progress": sum(
                        1
                        for task in tasks
                        if task.get("stage") == "evaluate"
                        and task.get("status") == "in_progress"
                    ),
                },
            },
        }

    def build_summary(self, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "task_count": len(tasks),
            "completed_count": sum(
                1 for task in tasks if task.get("status") == "completed"
            ),
            "failed_count": sum(1 for task in tasks if task.get("status") == "failed"),
            "skipped_count": sum(1 for task in tasks if task.get("status") == "skipped"),
            "fetch_completed_count": sum(
                1
                for task in tasks
                if task.get("stage") == "fetch"
                and task.get("status") == "completed"
            ),
            "extract_completed_count": sum(
                1
                for task in tasks
                if task.get("stage") == "extract"
                and task.get("status") == "completed"
            ),
            "evaluate_completed_count": sum(
                1
                for task in tasks
                if task.get("stage") == "evaluate"
                and task.get("status") == "completed"
            ),
        }
```

Update `backend/app/core/config.py` with:

```python
    candidate_fetch_concurrency: int = Field(default=2)
    candidate_extract_concurrency: int = Field(default=2)
    candidate_evaluate_concurrency: int = Field(default=2)
```

- [ ] **Step 4: Re-run the orchestrator unit tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py -q -k "orchestrator_creates_fetch_tasks or follow_up_tasks or runtime_summary_counts_statuses"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_tools_and_eval.py backend/app/agent/candidate_orchestrator.py backend/app/core/config.py
git commit -m "feat: add candidate task orchestrator core"
```

### Task 4: Refactor Extraction And Evaluation Into Candidate Task Workers

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/app/agent/extraction_agent.py`
- Modify: `backend/app/agent/evaluation_agent.py`

- [ ] **Step 1: Write the failing worker-entry tests**

Add the following tests to `backend/tests/test_tools_and_eval.py`:

```python
def test_extraction_agent_can_run_fetch_task() -> None:
    from app.agent.extraction_agent import ExtractionAgent
    from app.mcp.local_gateway import LocalToolGateway
    from app.tools.responses import ToolResponse

    gateway = LocalToolGateway()
    gateway.register(
        "fetch_article_content",
        lambda candidates: ToolResponse.success(
            tool_name="fetch_article_content",
            summary="Fetched candidate content.",
            data={
                "candidates": [
                    {
                        "candidate_id": "cand_001",
                        "title": "AI Agent funding update",
                        "content": "full content",
                        "fetch_status": "fetched",
                    }
                ]
            },
        ),
    )
    agent = ExtractionAgent(gateway=gateway)
    state = {
        "retrieval_output": {
            "candidate_pool": [
                {"candidate_id": "cand_001", "title": "AI Agent funding update"}
            ]
        },
        "fetched_contents": [],
        "tool_results": [],
        "errors": [],
        "events": [],
    }
    task = {
        "task_id": "run_x:fetch:cand_001",
        "candidate_id": "cand_001",
        "stage": "fetch",
    }

    result = agent.run_fetch_task(task, state)

    assert result["candidate_id"] == "cand_001"
    assert result["fetch_status"] == "fetched"
    assert state["fetched_contents"][0]["candidate_id"] == "cand_001"


def test_evaluation_agent_can_run_candidate_evaluate_task() -> None:
    from app.agent.evaluation_agent import EvaluationAgent
    from app.mcp.local_gateway import LocalToolGateway

    agent = EvaluationAgent(gateway=LocalToolGateway(), settings=None)
    state = {
        "topic": {"name": "AI Agent", "push_threshold": 0.7},
        "evaluation_output": {"scored_items": [], "final_decisions": [], "decision_reasons": []},
        "extracted_items": [
            {
                "candidate_id": "cand_001",
                "title": "AI Agent funding update",
                "summary": "Strong launch signal",
                "source_type": "search",
                "source_name": "Mock Search",
                "url": "https://example.com/funding",
            }
        ],
    }
    task = {
        "task_id": "run_x:evaluate:cand_001",
        "candidate_id": "cand_001",
        "stage": "evaluate",
    }

    result = agent.run_evaluate_task(task, state)

    assert result["candidate_id"] == "cand_001"
    assert "score" in result
    assert "should_push" in result
```

- [ ] **Step 2: Run the worker-entry tests to verify failure**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py -q -k "run_fetch_task or run_candidate_evaluate_task"
```

Expected: FAIL because the task-oriented worker methods do not exist yet.

- [ ] **Step 3: Add task-oriented worker entry points**

Update `backend/app/agent/extraction_agent.py` with methods shaped like:

```python
    def run_fetch_task(
        self,
        task: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        candidate_id = str(task["candidate_id"])
        candidate_pool = list(state.get("retrieval_output", {}).get("candidate_pool", []))
        matched = [
            dict(candidate)
            for candidate in candidate_pool
            if str(candidate.get("candidate_id")) == candidate_id
        ]
        if not matched:
            raise RuntimeError(f"candidate not found for fetch task: {candidate_id}")

        fetched = self.fetch_contents(
            {
                **state,
                "candidate_items": matched,
                "fetched_contents": list(state.get("fetched_contents", [])),
            }
        )["fetched_contents"]
        result = next(
            item for item in fetched if str(item.get("candidate_id")) == candidate_id
        )
        state["fetched_contents"] = list(fetched)
        return dict(result)

    def run_extract_task(
        self,
        task: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        candidate_id = str(task["candidate_id"])
        fetched_contents = list(state.get("fetched_contents", []))
        matched = [
            dict(candidate)
            for candidate in fetched_contents
            if str(candidate.get("candidate_id")) == candidate_id
        ]
        if not matched:
            raise RuntimeError(f"candidate not found for extract task: {candidate_id}")

        extracted = self.extract_evidence(
            {
                **state,
                "fetched_contents": matched,
                "extracted_items": list(state.get("extracted_items", [])),
            }
        )["extracted_items"]
        result = next(
            item for item in extracted if str(item.get("candidate_id")) == candidate_id
        )
        state["extracted_items"] = list(extracted)
        return dict(result)
```

Update `backend/app/agent/evaluation_agent.py` with a task worker entry point:

```python
    def run_evaluate_task(
        self,
        task: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        candidate_id = str(task["candidate_id"])
        extracted_items = list(state.get("extracted_items", []))
        matched = [
            dict(item)
            for item in extracted_items
            if str(item.get("candidate_id")) == candidate_id
        ]
        if not matched:
            raise RuntimeError(f"candidate not found for evaluate task: {candidate_id}")

        scoped_state = {
            **state,
            "extracted_items": matched,
            "deduped_items": list(matched),
        }
        result_state = self.run(scoped_state)
        decisions = list(result_state.get("final_decisions", []))
        result = next(
            item for item in decisions if str(item.get("candidate_id")) == candidate_id
        )

        evaluation_output = dict(state.get("evaluation_output", {}))
        evaluation_output["scored_items"] = list(
            state.get("scored_items", result_state.get("scored_items", []))
        )
        evaluation_output["final_decisions"] = list(
            state.get("final_decisions", result_state.get("final_decisions", []))
        )
        state["evaluation_output"] = evaluation_output
        state["scored_items"] = list(result_state.get("scored_items", []))
        state["final_decisions"] = list(result_state.get("final_decisions", []))
        return dict(result)
```

- [ ] **Step 4: Re-run the worker-entry tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py -q -k "run_fetch_task or run_candidate_evaluate_task"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_tools_and_eval.py backend/app/agent/extraction_agent.py backend/app/agent/evaluation_agent.py
git commit -m "feat: add candidate task worker entry points"
```

### Task 5: Integrate Candidate Orchestrator Into LangGraph Runtime

**Files:**
- Modify: `backend/tests/test_monitor_run_flow.py`
- Modify: `backend/app/agent/graph.py`
- Modify: `backend/app/agent/nodes.py`
- Modify: `backend/app/storage/repository.py`

- [ ] **Step 1: Write the failing monitor-flow orchestration tests**

Add the following tests to `backend/tests/test_monitor_run_flow.py`:

```python
def test_monitor_graph_runs_candidate_orchestrator_and_persists_task_ledger() -> None:
    class RecordingRepository(InMemoryMonitorRunRepository):
        def __init__(self) -> None:
            super().__init__()
            self.candidate_task_records: list[dict[str, object]] = []

        def create_candidate_task_records(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
            for payload in payloads:
                self.candidate_task_records.append(payload.__dict__)
            return list(self.candidate_task_records)

        def list_candidate_task_records(
            self,
            run_id: str,
            *,
            candidate_id: str | None = None,
        ) -> list[dict[str, object]]:
            records = [
                record for record in self.candidate_task_records if record["run_id"] == run_id
            ]
            if candidate_id is not None:
                records = [
                    record for record in records if record["candidate_id"] == candidate_id
                ]
            return records

    repository = RecordingRepository()
    state = {
        "run_id": "run_candidate_orchestration",
        "topic_id": "topic_ai",
        "topic": {"name": "AI Agent", "push_threshold": 0.7},
        "seed_keywords": ["AI Agent"],
        "expanded_queries": ["AI Agent"],
        "retrieval_output": {
            "candidate_pool": [
                {
                    "candidate_id": "cand_001",
                    "run_id": "run_candidate_orchestration",
                    "topic_id": "topic_ai",
                    "source_type": "search",
                    "source_name": "Mock Search",
                    "title": "AI Agent funding update",
                    "url": "https://example.com/funding",
                    "fetch_status": "pending",
                    "raw_summary": "funding summary",
                }
            ]
        },
        "candidate_items": [],
        "fetched_contents": [],
        "extracted_items": [],
        "scored_items": [],
        "final_decisions": [],
        "decision_reasons": [],
        "push_records": [],
        "tool_results": [],
        "events": [],
        "errors": [],
        "status": "running",
    }

    result = candidate_task_orchestrator_node(
        state,
        gateway=build_gateway_with_mock_fetch_and_extract_tools(),
        run_repository=repository,
        settings=Settings(
            database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
            redis_url="redis://localhost:6379/0",
            candidate_fetch_concurrency=2,
            candidate_extract_concurrency=1,
            candidate_evaluate_concurrency=1,
        ),
    )

    assert result["candidate_task_summary"]["task_count"] == 3
    assert result["candidate_task_summary"]["evaluate_completed_count"] == 1
    assert len(repository.candidate_task_records) == 3
    assert result["final_decisions"][0]["candidate_id"] == "cand_001"
    assert any(event["node"] == "candidate_task_orchestrator" for event in result["events"])


def test_candidate_orchestrator_records_failed_task_without_fake_success() -> None:
    repository = InMemoryMonitorRunRepository()
    state = {
        "run_id": "run_candidate_failure",
        "topic_id": "topic_ai",
        "topic": {"name": "AI Agent", "push_threshold": 0.7},
        "retrieval_output": {
            "candidate_pool": [
                {
                    "candidate_id": "cand_001",
                    "run_id": "run_candidate_failure",
                    "topic_id": "topic_ai",
                    "source_type": "search",
                    "source_name": "Mock Search",
                    "title": "AI Agent funding update",
                    "url": "https://example.com/funding",
                    "fetch_status": "pending",
                }
            ]
        },
        "candidate_items": [],
        "fetched_contents": [],
        "extracted_items": [],
        "scored_items": [],
        "final_decisions": [],
        "decision_reasons": [],
        "push_records": [],
        "tool_results": [],
        "events": [],
        "errors": [],
        "status": "running",
    }

    result = candidate_task_orchestrator_node(
        state,
        gateway=build_gateway_with_failing_fetch_tool(),
        run_repository=repository,
        settings=Settings(
            database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
            redis_url="redis://localhost:6379/0",
        ),
    )

    assert result["candidate_task_summary"]["failed_count"] == 1
    assert result["errors"][-1]["code"] == "tool_error"
    assert not result["final_decisions"]
```

- [ ] **Step 2: Run the orchestration monitor-flow tests to verify failure**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_monitor_run_flow.py -q -k "candidate_orchestrator_and_persists_task_ledger or records_failed_task_without_fake_success"
```

Expected: FAIL because the orchestrator node is not integrated into the runtime yet.

- [ ] **Step 3: Add the orchestrator node and graph integration**

Update `backend/app/agent/nodes.py` to add `candidate_task_orchestrator_node(...)` that:

```python
def candidate_task_orchestrator_node(
    state: dict[str, Any],
    *,
    gateway: ToolGateway,
    run_repository: MonitorRunRepositoryProtocol | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    orchestrator = CandidateTaskOrchestrator(
        fetch_concurrency=(
            settings.candidate_fetch_concurrency if settings else 2
        ),
        extract_concurrency=(
            settings.candidate_extract_concurrency if settings else 2
        ),
        evaluate_concurrency=(
            settings.candidate_evaluate_concurrency if settings else 2
        ),
    )
    extraction_agent = ExtractionAgent(gateway=gateway)
    evaluation_agent = EvaluationAgent(gateway=gateway, settings=settings)

    tasks = orchestrator.build_initial_tasks(state)
    completed_tasks: list[dict[str, Any]] = []
    failed_tasks: list[dict[str, Any]] = []
    queue = list(tasks)

    append_event(
        state,
        "candidate_task_orchestrator",
        "Started candidate task orchestration.",
        payload={"task_count": len(queue)},
    )

    while queue:
        task = queue.pop(0)
        try:
            if task["stage"] == "fetch":
                result = extraction_agent.run_fetch_task(task, state)
                state["candidate_items"] = list(state.get("retrieval_output", {}).get("candidate_pool", []))
                output_ref = {"fetched_candidate_id": str(result["candidate_id"])}
            elif task["stage"] == "extract":
                result = extraction_agent.run_extract_task(task, state)
                output_ref = {"extracted_candidate_id": str(result["candidate_id"])}
            else:
                result = evaluation_agent.run_evaluate_task(task, state)
                output_ref = {"decision_candidate_id": str(result["candidate_id"])}

            completed = orchestrator.mark_task_completed(task, output_ref=output_ref)
            completed_tasks.append(completed)
            queue.extend(orchestrator.build_follow_up_tasks(completed))
        except Exception as exc:
            failed = dict(task)
            failed["status"] = "failed"
            failed["error_code"] = "tool_error"
            failed["error_message"] = str(exc)
            failed["finished_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            failed_tasks.append(failed)
            errors = list(state.get("errors", []))
            errors.append(
                {
                    "tool_name": "candidate_task_orchestrator",
                    "code": "tool_error",
                    "message": str(exc),
                    "details": {
                        "candidate_id": task["candidate_id"],
                        "stage": task["stage"],
                    },
                }
            )
            state["errors"] = errors

    all_tasks = completed_tasks + failed_tasks
    state["candidate_task_plan"] = list(all_tasks)
    state["candidate_task_runtime"] = orchestrator.build_runtime_view(all_tasks)
    state["candidate_task_summary"] = orchestrator.build_summary(all_tasks)

    if run_repository is not None and all_tasks:
        run_repository.create_candidate_task_records(
            tuple(
                CandidateTaskRecordCreateData(
                    task_id=str(task["task_id"]),
                    run_id=str(task["run_id"]),
                    candidate_id=str(task["candidate_id"]),
                    stage=str(task["stage"]),
                    status=str(task["status"]),
                    attempt=int(task.get("attempt", 1)),
                    max_attempts=int(task.get("max_attempts", 1)),
                    depends_on_task_ids=tuple(str(item) for item in task.get("depends_on_task_ids", [])),
                    input_ref=dict(task.get("input_ref", {})),
                    output_ref=dict(task.get("output_ref", {})),
                    error_code=task.get("error_code"),
                    error_message=task.get("error_message"),
                    started_at=None,
                    finished_at=None,
                )
                for task in all_tasks
            )
        )

    append_event(
        state,
        "candidate_task_orchestrator",
        "Completed candidate task orchestration.",
        payload=dict(state["candidate_task_summary"]),
    )
    return state
```

Update `backend/app/agent/graph.py` so the graph becomes:

```python
    graph.add_node(
        "candidate_task_orchestrator",
        lambda state: candidate_task_orchestrator_node(
            state,
            gateway=resolved_gateway,
            run_repository=run_repository,
            settings=settings,
        ),
    )
```

and edges become:

```python
    graph.add_edge("retrieval_agent", "candidate_task_orchestrator")
    graph.add_edge("candidate_task_orchestrator", "supervisor_finalize")
```

Keep `supervisor_finalize` as the persistence and summary closure node.

- [ ] **Step 4: Re-run the orchestration monitor-flow tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_monitor_run_flow.py -q -k "candidate_orchestrator_and_persists_task_ledger or records_failed_task_without_fake_success"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_monitor_run_flow.py backend/app/agent/graph.py backend/app/agent/nodes.py backend/app/storage/repository.py
git commit -m "feat: integrate candidate orchestrator into monitor graph"
```

### Task 6: Add Task Ledger Readback And Run Detail Evidence

**Files:**
- Modify: `backend/tests/test_monitor_run_flow.py`
- Modify: `backend/app/schemas/monitor_schema.py`
- Modify: `backend/app/api/monitor.py`
- Modify: `backend/README.md`

- [ ] **Step 1: Write the failing readback tests**

Add the following tests to `backend/tests/test_monitor_run_flow.py`:

```python
def test_run_detail_api_returns_candidate_task_summary_and_ledger(client: TestClient) -> None:
    topic_response = client.post(
        "/api/topics",
        json={
            "name": "AI Agent",
            "description": "Track AI agent launches.",
            "seed_keywords": ["AI Agent"],
            "trusted_sources": ["example.com"],
            "exclude_keywords": [],
            "push_threshold": 0.7,
            "cooldown_hours": 24,
            "enabled": True,
            "schedule_cron": "0 */6 * * *",
        },
    )
    topic_id = topic_response.json()["topic_id"]
    run_response = client.post(f"/api/monitor/{topic_id}/run")
    run_id = run_response.json()["run_id"]

    detail = client.get(f"/api/monitor/runs/{run_id}")
    task_records = client.get(f"/api/monitor/runs/{run_id}/candidate-tasks")

    assert detail.status_code == 200
    assert task_records.status_code == 200
    assert "candidate_task_summary" in detail.json()
    assert "items" in task_records.json()


def test_run_detail_api_can_filter_candidate_task_records_by_candidate(client: TestClient) -> None:
    response = client.get("/api/monitor/runs/run_seeded/candidate-tasks", params={"candidate_id": "cand_001"})

    assert response.status_code == 200
    assert all(item["candidate_id"] == "cand_001" for item in response.json()["items"])
```

- [ ] **Step 2: Run the readback tests to verify failure**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_monitor_run_flow.py -q -k "candidate_task_summary_and_ledger or filter_candidate_task_records_by_candidate"
```

Expected: FAIL because the API and schema do not expose task ledger readback yet.

- [ ] **Step 3: Add task ledger API and schema support**

Update `backend/app/schemas/monitor_schema.py` to extend the run detail response and add:

```python
class CandidateTaskRecordResponse(BaseModel):
    task_id: str
    run_id: str
    candidate_id: str
    stage: str
    status: str
    attempt: int
    max_attempts: int
    depends_on_task_ids: list[str]
    input_ref: dict[str, Any]
    output_ref: dict[str, Any]
    error_code: str | None = None
    error_message: str | None = None


class CandidateTaskRecordListResponse(BaseModel):
    items: list[CandidateTaskRecordResponse]
```

Extend `MonitorRunStateResponse` with:

```python
    candidate_task_summary: dict[str, Any] = Field(default_factory=dict)
```

Update `backend/app/api/monitor.py` `get_run_state()` to return:

```python
        candidate_task_summary=dict(snapshot.get("candidate_task_summary", {})),
```

Add a new route:

```python
@router.get(
    "/runs/{run_id}/candidate-tasks",
    response_model=CandidateTaskRecordListResponse,
)
def list_run_candidate_tasks(
    run_id: str,
    candidate_id: str | None = None,
    repository: Annotated[
        MonitorRunRepositoryProtocol,
        Depends(get_monitor_run_repository),
    ] = None,
) -> CandidateTaskRecordListResponse:
    run_record = repository.get_monitor_run(run_id)
    if run_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monitor run not found",
        )

    items = repository.list_candidate_task_records(
        run_id,
        candidate_id=candidate_id,
    )
    return CandidateTaskRecordListResponse(items=items)
```

Update `backend/README.md` to document:

```markdown
- Candidate-level orchestration runs inside the LangGraph monitor flow after retrieval.
- Redis/runtime state owns short-lived candidate task coordination.
- PostgreSQL persists candidate task ledger facts for historical readback.
- `GET /api/monitor/runs/{run_id}/candidate-tasks` exposes durable task evidence.
```

- [ ] **Step 4: Re-run the readback tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_monitor_run_flow.py -q -k "candidate_task_summary_and_ledger or filter_candidate_task_records_by_candidate"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_monitor_run_flow.py backend/app/schemas/monitor_schema.py backend/app/api/monitor.py backend/README.md
git commit -m "feat: expose candidate task orchestration evidence"
```

### Task 7: Run Full Candidate Orchestration Verification

**Files:**
- Modify: `backend/README.md`
- Modify: any touched backend files needed for final integration fixes

- [ ] **Step 1: Run focused candidate orchestration regressions**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py tests/test_monitor_run_flow.py -q -k "candidate_task or orchestrator or run_fetch_task or run_candidate_evaluate_task"
```

Expected: PASS.

- [ ] **Step 2: Run the foundation-plus-orchestration suite**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py tests/test_monitor_run_flow.py tests/test_topics_api.py tests/test_health_api.py -q
```

Expected: PASS.

- [ ] **Step 3: Run the full backend suite**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest -q
```

Expected: PASS.

- [ ] **Step 4: Verify repo hygiene**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp
git diff --check
git status --short
```

Expected: no whitespace errors and only intended candidate-orchestration changes remain.

- [ ] **Step 5: Commit the orchestration milestone**

```bash
git add backend
git commit -m "feat: add candidate orchestration runtime"
```

## Self-Review

### Spec Coverage

- candidate-level task model: covered by Tasks 1-3
- PostgreSQL task ledger: covered by Task 2
- worker role refactor: covered by Task 4
- LangGraph integration: covered by Task 5
- API-visible task evidence: covered by Task 6
- verification and milestone closure: covered by Task 7

No accepted requirement from the candidate orchestration spec is left without a task.

### Placeholder Scan

- No `TBD`, `TODO`, or deferred filler steps remain.
- Each task includes explicit files, commands, expected outcomes, and commit points.

### Type Consistency

- Candidate task contracts consistently use `task_id`, `candidate_id`, `stage`, `status`, `attempt`, and `max_attempts`.
- The task ledger consistently uses `CandidateTaskRecordCreateData`.
- The orchestration state consistently uses `candidate_task_plan`, `candidate_task_runtime`, and `candidate_task_summary`.
