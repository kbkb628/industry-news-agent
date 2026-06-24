from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.agent.graph import build_monitor_graph
from app.api.monitor import _build_initial_state
from app.core.config import Settings
from app.llm.mock_client import MockLLM
from app.storage.database import Base, get_engine
from app.storage.models import (
    CandidateRecord,
    CandidateTaskRecord,
    DecisionRecord,
    EvalResult,
    ExtractedItemRecord,
    MonitorRun,
    PushRecord,
    RunEvent,
    Topic,
)
from app.storage.repository import (
    MonitorRunRepositoryProtocol,
    TopicCreateData,
    TopicRecord,
    TopicRepositoryProtocol,
    build_monitor_run_repository,
    build_topic_repository,
)

DEMO_TOPIC_NAME = "AI Agent"
DEMO_TOPIC_DESCRIPTION = "Track enterprise AI agent launches and deployment updates."
DEMO_SEED_KEYWORDS = ("OpenAI", "enterprise", "automation")
DEMO_TRUSTED_SOURCES = ("AI Daily RSS", "AI Search")
DEMO_EXCLUDE_KEYWORDS = ("rumor",)
DEMO_PUSH_THRESHOLD = 0.72
DEMO_COOLDOWN_HOURS = 24
DEMO_TOPIC_ID = "topic_ai_agent"
DEMO_RUN_ID = "run_demo_bootstrap"


@dataclass(frozen=True, slots=True)
class DemoBootstrapResult:
    topic_id: str
    run_id: str
    candidate_count: int
    push_count: int
    event_count: int
    candidate_task_count: int


def _build_demo_topic_payload() -> TopicCreateData:
    return TopicCreateData(
        name=DEMO_TOPIC_NAME,
        description=DEMO_TOPIC_DESCRIPTION,
        seed_keywords=DEMO_SEED_KEYWORDS,
        trusted_sources=DEMO_TRUSTED_SOURCES,
        exclude_keywords=DEMO_EXCLUDE_KEYWORDS,
        push_threshold=DEMO_PUSH_THRESHOLD,
        cooldown_hours=DEMO_COOLDOWN_HOURS,
        enabled=True,
        schedule_cron="0 */6 * * *",
    )


def _get_or_create_demo_topic(
    session: Session,
    topic_repository: TopicRepositoryProtocol,
) -> TopicRecord:
    existing = topic_repository.get_topic(DEMO_TOPIC_ID)
    if existing is not None:
        return existing

    topic = Topic(
        topic_id=DEMO_TOPIC_ID,
        name=DEMO_TOPIC_NAME,
        description=DEMO_TOPIC_DESCRIPTION,
        seed_keywords=list(DEMO_SEED_KEYWORDS),
        trusted_sources=list(DEMO_TRUSTED_SOURCES),
        exclude_keywords=list(DEMO_EXCLUDE_KEYWORDS),
        push_threshold=DEMO_PUSH_THRESHOLD,
        cooldown_hours=DEMO_COOLDOWN_HOURS,
        enabled=True,
        schedule_cron="0 */6 * * *",
    )
    session.add(topic)
    session.commit()
    session.refresh(topic)
    return TopicRecord(
        topic_id=topic.topic_id,
        name=topic.name,
        description=topic.description,
        seed_keywords=tuple(topic.seed_keywords),
        trusted_sources=tuple(topic.trusted_sources),
        exclude_keywords=tuple(topic.exclude_keywords),
        push_threshold=topic.push_threshold,
        cooldown_hours=topic.cooldown_hours,
        enabled=topic.enabled,
        schedule_cron=topic.schedule_cron,
        created_at=topic.created_at,
        updated_at=topic.updated_at,
    )


def _reset_demo_run(session: Session) -> None:
    session.query(CandidateTaskRecord).filter_by(run_id=DEMO_RUN_ID).delete()
    session.query(PushRecord).filter_by(run_id=DEMO_RUN_ID).delete()
    session.query(RunEvent).filter_by(run_id=DEMO_RUN_ID).delete()
    session.query(EvalResult).filter_by(run_id=DEMO_RUN_ID).delete()
    session.query(DecisionRecord).filter_by(run_id=DEMO_RUN_ID).delete()
    session.query(ExtractedItemRecord).filter_by(run_id=DEMO_RUN_ID).delete()
    session.query(CandidateRecord).filter_by(run_id=DEMO_RUN_ID).delete()
    session.query(MonitorRun).filter_by(run_id=DEMO_RUN_ID).delete()
    session.commit()


def _run_demo_graph(
    *,
    topic: TopicRecord,
    run_repository: MonitorRunRepositoryProtocol,
    settings: Settings,
) -> dict[str, Any]:
    initial_state = _build_initial_state(topic, DEMO_RUN_ID)
    graph = build_monitor_graph(
        llm=MockLLM(),
        run_repository=run_repository,
        settings=settings,
    )
    return graph.invoke(initial_state)


def bootstrap_demo_run(
    *,
    session_factory: sessionmaker[Session],
    settings: Settings,
) -> DemoBootstrapResult:
    Base.metadata.create_all(get_engine(settings))
    with session_factory() as session:
        topic_repository = build_topic_repository(session)
        run_repository = build_monitor_run_repository(session)
        topic = _get_or_create_demo_topic(session, topic_repository)
        _reset_demo_run(session)
        state = _run_demo_graph(
            topic=topic,
            run_repository=run_repository,
            settings=settings,
        )
        session.commit()

        candidate_count = len(run_repository.list_candidate_records(DEMO_RUN_ID))
        push_count = len(run_repository.list_push_records(run_id=DEMO_RUN_ID))
        event_count = len(run_repository.list_run_events(DEMO_RUN_ID))
        candidate_task_count = len(
            run_repository.list_candidate_task_records(DEMO_RUN_ID)
        )

    return DemoBootstrapResult(
        topic_id=topic.topic_id,
        run_id=str(state["run_id"]),
        candidate_count=candidate_count,
        push_count=push_count,
        event_count=event_count,
        candidate_task_count=candidate_task_count,
    )
