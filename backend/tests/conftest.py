from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.storage.database import Base, build_engine, build_session_factory, get_db
from app.storage.repository import (
    CandidateRecordUpsertData,
    DecisionRecordUpsertData,
    EvalResultCreateData,
    ExtractedItemRecordUpsertData,
    MonitorRunUpsertData,
    PushRecordCreateData,
    RunEventCreateData,
    TopicCreateData,
    build_monitor_run_repository,
    build_topic_repository,
)


@dataclass(frozen=True, slots=True)
class SeededPhaseAArtifacts:
    database_url: str
    session_factory: sessionmaker[Session]
    topic_id: str
    run_id: str


def _build_phase_a_topic_create_data() -> TopicCreateData:
    return TopicCreateData(
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


def _seed_phase_a_persisted_artifacts(
    session_factory: sessionmaker[Session],
) -> tuple[str, str]:
    run_id = "run_phase_a"

    with session_factory() as session:
        topic_repository = build_topic_repository(session)
        run_repository = build_monitor_run_repository(session)
        topic = topic_repository.create_topic(_build_phase_a_topic_create_data())

        run_repository.upsert_monitor_run(
            MonitorRunUpsertData(
                run_id=run_id,
                topic_id=topic.topic_id,
                status="completed",
                state_snapshot={
                    "run_id": run_id,
                    "topic_id": topic.topic_id,
                    "trigger": "scheduler",
                    "status": "completed",
                    "candidate_items": [
                        {
                            "candidate_id": "cand_001",
                            "title": "OpenAI agent update",
                            "url": "https://example.com/agent-update",
                        }
                    ],
                    "final_decisions": [
                        {
                            "candidate_id": "cand_001",
                            "should_push": True,
                            "decision_reason": "Above threshold",
                        }
                    ],
                    "errors": [],
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
                    run_id=run_id,
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
                    run_id=run_id,
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
                    run_id=run_id,
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
                    run_id=run_id,
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
                    run_id=run_id,
                    topic_id=topic.topic_id,
                    event_type="notification_sent",
                    node="notification_send",
                    message="Run completed.",
                    payload={"status": "completed"},
                    elapsed_ms=3210,
                ),
            )
        )
        run_repository.create_eval_result(
            EvalResultCreateData(
                run_id=run_id,
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

    return topic.topic_id, run_id


@pytest.fixture
def seeded_phase_a_sqlalchemy(tmp_path: Path) -> Iterator[SeededPhaseAArtifacts]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'phase_a_foundation.db'}"
    settings = Settings(
        database_url=database_url,
        redis_url="redis://localhost:6379/0",
    )
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    topic_id, run_id = _seed_phase_a_persisted_artifacts(session_factory)

    try:
        yield SeededPhaseAArtifacts(
            database_url=database_url,
            session_factory=session_factory,
            topic_id=topic_id,
            run_id=run_id,
        )
    finally:
        engine.dispose()


@pytest.fixture
def sqlalchemy_client_factory() -> Callable[[sessionmaker[Session]], Iterator[TestClient]]:
    @contextmanager
    def _build_client(
        session_factory: sessionmaker[Session],
    ) -> Iterator[TestClient]:
        app = create_app()

        @asynccontextmanager
        async def _noop_lifespan(_app: object) -> Iterator[None]:
            yield

        def _override_get_db() -> Iterator[Session]:
            session = session_factory()
            try:
                yield session
            finally:
                session.close()

        app.router.lifespan_context = _noop_lifespan
        app.dependency_overrides[get_db] = _override_get_db
        with TestClient(app) as test_client:
            yield test_client
        app.dependency_overrides.clear()

    return _build_client


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
