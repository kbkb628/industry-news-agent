from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.schemas.topic_schema import TopicCreateRequest, TopicResponse
from app.storage.database import get_db
from app.storage.repository import (
    TopicCreateData,
    TopicRepositoryProtocol,
    build_topic_repository,
)

router = APIRouter(prefix="/api/topics", tags=["topics"])


class TopicCreatedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: str
    status: Literal["created"]
    created_at: datetime


def get_topic_repository(
    session: Annotated[Session, Depends(get_db)],
) -> TopicRepositoryProtocol:
    return build_topic_repository(session)


def _to_create_data(payload: TopicCreateRequest) -> TopicCreateData:
    return TopicCreateData(
        name=payload.name,
        description=payload.description,
        seed_keywords=tuple(payload.seed_keywords),
        trusted_sources=tuple(payload.trusted_sources),
        exclude_keywords=tuple(payload.exclude_keywords),
        push_threshold=payload.push_threshold,
        cooldown_hours=payload.cooldown_hours,
        enabled=payload.enabled,
        schedule_cron=payload.schedule_cron,
    )


@router.post(
    "",
    response_model=TopicCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_topic(
    payload: TopicCreateRequest,
    repository: Annotated[TopicRepositoryProtocol, Depends(get_topic_repository)],
) -> TopicCreatedResponse:
    topic = repository.create_topic(_to_create_data(payload))
    return TopicCreatedResponse(
        topic_id=topic.topic_id,
        status="created",
        created_at=topic.created_at,
    )


@router.get("", response_model=list[TopicResponse])
def list_topics(
    repository: Annotated[TopicRepositoryProtocol, Depends(get_topic_repository)],
) -> list[TopicResponse]:
    return [TopicResponse.model_validate(topic) for topic in repository.list_topics()]


@router.get("/{topic_id}", response_model=TopicResponse)
def get_topic(
    topic_id: str,
    repository: Annotated[TopicRepositoryProtocol, Depends(get_topic_repository)],
) -> TopicResponse:
    topic = repository.get_topic(topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return TopicResponse.model_validate(topic)
