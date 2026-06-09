from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import DEFAULT_PUSH_THRESHOLD
from app.main import create_app
from app.storage.repository import SqlAlchemyTopicRepository, TopicCreateData, TopicRecord


class FakeTopicRepository:
    def __init__(self) -> None:
        self._records: list[TopicRecord] = []

    def create_topic(self, payload: TopicCreateData) -> TopicRecord:
        timestamp = datetime(2026, 6, 9, tzinfo=UTC)
        record = TopicRecord(
            topic_id=f"topic_{len(self._records) + 1:03d}",
            name=payload.name,
            description=payload.description,
            seed_keywords=payload.seed_keywords,
            trusted_sources=payload.trusted_sources,
            exclude_keywords=payload.exclude_keywords,
            push_threshold=payload.push_threshold,
            cooldown_hours=payload.cooldown_hours,
            enabled=payload.enabled,
            schedule_cron=payload.schedule_cron,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._records.append(record)
        return record

    def list_topics(self) -> list[TopicRecord]:
        return sorted(
            self._records,
            key=lambda record: (record.created_at, record.topic_id),
        )

    def get_topic(self, topic_id: str) -> TopicRecord | None:
        for record in self._records:
            if record.topic_id == topic_id:
                return record
        return None


@contextmanager
def _build_client(repository: FakeTopicRepository) -> Iterator[TestClient]:
    from app.api.topics import get_topic_repository

    app = create_app()
    app.dependency_overrides[get_topic_repository] = lambda: repository
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_create_topic_returns_creation_receipt() -> None:
    repository = FakeTopicRepository()

    with _build_client(repository) as client:
        response = client.post(
            "/api/topics",
            json={
                "name": "AI Agent",
                "description": "Track launches and financings.",
                "seed_keywords": ["AI Agent", "MCP"],
                "trusted_sources": ["github.com"],
                "exclude_keywords": ["advertorial"],
                "push_threshold": 0.81,
                "cooldown_hours": 8,
                "enabled": True,
                "schedule_cron": "0 */6 * * *",
            },
        )

    assert response.status_code == 201
    assert response.json() == {
        "topic_id": "topic_001",
        "status": "created",
        "created_at": "2026-06-09T00:00:00Z",
    }


def test_topics_html_page_renders() -> None:
    repository = FakeTopicRepository()

    with _build_client(repository) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "行业资讯结构化推送智能体" in response.text
    assert "监控主题" in response.text


def test_admin_html_pages_render() -> None:
    repository = FakeTopicRepository()

    with _build_client(repository) as client:
        pushes_response = client.get("/pushes")
        run_detail_response = client.get("/runs/run_demo_001")
        events_response = client.get("/runs/run_demo_001/events")

    assert pushes_response.status_code == 200
    assert "推送记录" in pushes_response.text
    assert run_detail_response.status_code == 200
    assert "运行状态" in run_detail_response.text
    assert "run_demo_001" in run_detail_response.text
    assert events_response.status_code == 200
    assert "事件时间线" in events_response.text
    assert "run_demo_001" in events_response.text


@pytest.mark.parametrize("failing_method", ["commit", "refresh"])
def test_create_topic_rolls_back_session_when_persistence_fails(
    failing_method: str,
) -> None:
    class FakeSession:
        def __init__(self, failing_method: str) -> None:
            self.failing_method = failing_method
            self.rollback_calls = 0

        def add(self, topic: object) -> None:
            self.topic = topic

        def commit(self) -> None:
            if self.failing_method == "commit":
                raise SQLAlchemyError("commit failed")

        def refresh(self, topic: object) -> None:
            if self.failing_method == "refresh":
                raise SQLAlchemyError("refresh failed")

        def rollback(self) -> None:
            self.rollback_calls += 1

    session = FakeSession(failing_method=failing_method)
    repository = SqlAlchemyTopicRepository(session=session)  # type: ignore[arg-type]

    with pytest.raises(SQLAlchemyError):
        repository.create_topic(
            TopicCreateData(
                name="AI Agent",
                description="Track launches and financings.",
                seed_keywords=("AI Agent",),
                trusted_sources=("github.com",),
                exclude_keywords=("advertorial",),
                push_threshold=DEFAULT_PUSH_THRESHOLD,
                cooldown_hours=24,
                enabled=True,
                schedule_cron=None,
            )
        )

    assert session.rollback_calls == 1


def test_list_topics_returns_created_topics() -> None:
    repository = FakeTopicRepository()
    created = repository.create_topic(
        TopicCreateData(
            name="AI Agent",
            description="Track launches and financings.",
            seed_keywords=("AI Agent",),
            trusted_sources=("github.com",),
            exclude_keywords=("advertorial",),
            push_threshold=DEFAULT_PUSH_THRESHOLD,
            cooldown_hours=24,
            enabled=True,
            schedule_cron=None,
        )
    )
    second = repository.create_topic(
        TopicCreateData(
            name="Robotics",
            description="Track robotics funding.",
            seed_keywords=("robotics",),
            trusted_sources=("theverge.com",),
            exclude_keywords=(),
            push_threshold=0.9,
            cooldown_hours=12,
            enabled=False,
            schedule_cron="0 9 * * *",
        )
    )

    with _build_client(repository) as client:
        response = client.get("/api/topics")

    assert response.status_code == 200
    assert response.json() == [
        {
            "topic_id": created.topic_id,
            "name": "AI Agent",
            "description": "Track launches and financings.",
            "seed_keywords": ["AI Agent"],
            "trusted_sources": ["github.com"],
            "exclude_keywords": ["advertorial"],
            "push_threshold": DEFAULT_PUSH_THRESHOLD,
            "cooldown_hours": 24,
            "enabled": True,
            "schedule_cron": None,
            "created_at": "2026-06-09T00:00:00Z",
            "updated_at": "2026-06-09T00:00:00Z",
        },
        {
            "topic_id": second.topic_id,
            "name": "Robotics",
            "description": "Track robotics funding.",
            "seed_keywords": ["robotics"],
            "trusted_sources": ["theverge.com"],
            "exclude_keywords": [],
            "push_threshold": 0.9,
            "cooldown_hours": 12,
            "enabled": False,
            "schedule_cron": "0 9 * * *",
            "created_at": "2026-06-09T00:00:00Z",
            "updated_at": "2026-06-09T00:00:00Z",
        },
    ]


def test_get_topic_returns_matching_topic() -> None:
    repository = FakeTopicRepository()
    created = repository.create_topic(
        TopicCreateData(
            name="AI Agent",
            description="Track launches and financings.",
            seed_keywords=("AI Agent",),
            trusted_sources=("github.com",),
            exclude_keywords=(),
            push_threshold=DEFAULT_PUSH_THRESHOLD,
            cooldown_hours=24,
            enabled=True,
            schedule_cron=None,
        )
    )

    with _build_client(repository) as client:
        response = client.get(f"/api/topics/{created.topic_id}")

    assert response.status_code == 200
    assert response.json() == {
        "topic_id": created.topic_id,
        "name": "AI Agent",
        "description": "Track launches and financings.",
        "seed_keywords": ["AI Agent"],
        "trusted_sources": ["github.com"],
        "exclude_keywords": [],
        "push_threshold": DEFAULT_PUSH_THRESHOLD,
        "cooldown_hours": 24,
        "enabled": True,
        "schedule_cron": None,
        "created_at": "2026-06-09T00:00:00Z",
        "updated_at": "2026-06-09T00:00:00Z",
    }


def test_get_topic_returns_404_when_missing() -> None:
    repository = FakeTopicRepository()

    with _build_client(repository) as client:
        response = client.get("/api/topics/topic_missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Topic not found"}
