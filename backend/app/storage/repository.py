from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class TopicCreateData:
    name: str
    description: str
    seed_keywords: tuple[str, ...]
    trusted_sources: tuple[str, ...]
    exclude_keywords: tuple[str, ...]
    push_threshold: float
    cooldown_hours: int
    enabled: bool
    schedule_cron: str | None = None


@dataclass(frozen=True, slots=True)
class TopicRecord:
    topic_id: str
    name: str
    description: str
    seed_keywords: tuple[str, ...]
    trusted_sources: tuple[str, ...]
    exclude_keywords: tuple[str, ...]
    push_threshold: float
    cooldown_hours: int
    enabled: bool
    schedule_cron: str | None
    created_at: datetime
    updated_at: datetime


class TopicRepositoryProtocol(Protocol):
    def create_topic(self, payload: TopicCreateData) -> TopicRecord: ...

    def list_topics(self) -> list[TopicRecord]: ...

    def get_topic(self, topic_id: str) -> TopicRecord | None: ...


class UnimplementedTopicRepository:
    def __init__(self, session: Session | None = None) -> None:
        self.session = session

    def create_topic(self, payload: TopicCreateData) -> TopicRecord:
        raise NotImplementedError(
            "TopicRepository persistence is deferred to task 4."
        )

    def list_topics(self) -> list[TopicRecord]:
        raise NotImplementedError(
            "TopicRepository persistence is deferred to task 4."
        )

    def get_topic(self, topic_id: str) -> TopicRecord | None:
        raise NotImplementedError(
            "TopicRepository persistence is deferred to task 4."
        )


def build_topic_repository(session: Session | None = None) -> TopicRepositoryProtocol:
    return UnimplementedTopicRepository(session=session)
