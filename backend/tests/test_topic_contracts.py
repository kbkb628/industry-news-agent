from __future__ import annotations

from dataclasses import is_dataclass
from datetime import UTC, datetime
from typing import get_type_hints

import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_PUSH_THRESHOLD
from app.schemas.topic_schema import TopicCreateRequest, TopicResponse
from app.storage.models import Topic
from app.storage.repository import (
    TopicCreateData,
    TopicRecord,
    TopicRepositoryProtocol,
    UnimplementedTopicRepository,
    build_topic_repository,
)


def test_topic_create_request_defaults_and_contract_fields() -> None:
    payload = TopicCreateRequest(
        name="AI Agent",
        description="Track product launches, financing, and open-source releases.",
        seed_keywords=["AI Agent", "MCP"],
        trusted_sources=["github.com", "techcrunch.com"],
        exclude_keywords=["advertorial"],
    )

    assert set(payload.model_dump().keys()) == {
        "name",
        "description",
        "seed_keywords",
        "trusted_sources",
        "exclude_keywords",
        "push_threshold",
        "cooldown_hours",
        "enabled",
        "schedule_cron",
    }
    assert payload.push_threshold == DEFAULT_PUSH_THRESHOLD
    assert payload.cooldown_hours == 24
    assert payload.enabled is True
    assert payload.schedule_cron is None


def test_topic_response_supports_model_validate_from_sqlalchemy_object() -> None:
    timestamp = datetime(2026, 6, 9, tzinfo=UTC)
    orm_topic = Topic(
        topic_id="topic_001",
        name="AI Agent",
        description="Track product launches, financing, and open-source releases.",
        seed_keywords=["AI Agent", "MCP"],
        trusted_sources=["github.com"],
        exclude_keywords=["advertorial"],
        push_threshold=0.8,
        cooldown_hours=12,
        enabled=True,
        schedule_cron="0 */6 * * *",
        created_at=timestamp,
        updated_at=timestamp,
    )

    payload = TopicResponse.model_validate(orm_topic)

    assert payload.topic_id == "topic_001"
    assert payload.push_threshold == 0.8


def test_repository_contract_types_are_storage_focused() -> None:
    assert is_dataclass(TopicCreateData)
    assert is_dataclass(TopicRecord)

    create_hints = get_type_hints(TopicRepositoryProtocol.create_topic)
    list_hints = get_type_hints(TopicRepositoryProtocol.list_topics)
    get_hints = get_type_hints(TopicRepositoryProtocol.get_topic)

    assert create_hints["payload"] is TopicCreateData
    assert create_hints["return"] is TopicRecord
    assert list_hints["return"] == list[TopicRecord]
    assert get_hints["return"] == TopicRecord | None


def test_repository_placeholder_raises_for_storage_contract_calls() -> None:
    repository = build_topic_repository()
    payload = TopicCreateData(
        name="AI Agent",
        description="Track product launches, financing, and open-source releases.",
        seed_keywords=("AI Agent",),
        trusted_sources=("github.com",),
        exclude_keywords=(),
        push_threshold=DEFAULT_PUSH_THRESHOLD,
        cooldown_hours=24,
        enabled=True,
        schedule_cron=None,
    )

    with pytest.raises(NotImplementedError):
        repository.create_topic(payload)
    with pytest.raises(NotImplementedError):
        repository.list_topics()
    with pytest.raises(NotImplementedError):
        repository.get_topic("topic_001")

    assert isinstance(repository, UnimplementedTopicRepository)
