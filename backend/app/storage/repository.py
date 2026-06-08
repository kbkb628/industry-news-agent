from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import Topic


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


def _to_topic_record(model: Topic) -> TopicRecord:
    return TopicRecord(
        topic_id=model.topic_id,
        name=model.name,
        description=model.description,
        seed_keywords=tuple(model.seed_keywords),
        trusted_sources=tuple(model.trusted_sources),
        exclude_keywords=tuple(model.exclude_keywords),
        push_threshold=model.push_threshold,
        cooldown_hours=model.cooldown_hours,
        enabled=model.enabled,
        schedule_cron=model.schedule_cron,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyTopicRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_topic(self, payload: TopicCreateData) -> TopicRecord:
        topic = Topic(
            name=payload.name,
            description=payload.description,
            seed_keywords=list(payload.seed_keywords),
            trusted_sources=list(payload.trusted_sources),
            exclude_keywords=list(payload.exclude_keywords),
            push_threshold=payload.push_threshold,
            cooldown_hours=payload.cooldown_hours,
            enabled=payload.enabled,
            schedule_cron=payload.schedule_cron,
        )
        self.session.add(topic)
        try:
            self.session.commit()
            self.session.refresh(topic)
        except SQLAlchemyError:
            self.session.rollback()
            raise
        return _to_topic_record(topic)

    def list_topics(self) -> list[TopicRecord]:
        topics = self.session.scalars(
            select(Topic).order_by(Topic.created_at.asc(), Topic.topic_id.asc())
        ).all()
        return [_to_topic_record(topic) for topic in topics]

    def get_topic(self, topic_id: str) -> TopicRecord | None:
        topic = self.session.get(Topic, topic_id)
        if topic is None:
            return None
        return _to_topic_record(topic)


def build_topic_repository(session: Session | None = None) -> TopicRepositoryProtocol:
    if session is None:
        return UnimplementedTopicRepository(session=session)
    return SqlAlchemyTopicRepository(session=session)
