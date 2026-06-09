import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import DEFAULT_PUSH_THRESHOLD
from app.storage.database import Base


def _generate_topic_id() -> str:
    return f"topic_{uuid.uuid4().hex[:12]}"


class Topic(Base):
    __tablename__ = "topics"

    topic_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=_generate_topic_id,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    seed_keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    trusted_sources: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    exclude_keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    push_threshold: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=DEFAULT_PUSH_THRESHOLD,
    )
    cooldown_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    schedule_cron: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


def _generate_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


def _generate_push_id() -> str:
    return f"push_{uuid.uuid4().hex[:12]}"


def _generate_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"


def _generate_eval_id() -> str:
    return f"eval_{uuid.uuid4().hex[:12]}"


class MonitorRun(Base):
    __tablename__ = "monitor_runs"

    run_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=_generate_run_id,
    )
    topic_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    state_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PushRecord(Base):
    __tablename__ = "push_records"

    push_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=_generate_push_id,
    )
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    topic_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    should_push: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class RunEvent(Base):
    __tablename__ = "run_events"

    event_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=_generate_event_id,
    )
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    topic_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    node: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class EvalResult(Base):
    __tablename__ = "eval_results"

    eval_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=_generate_eval_id,
    )
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    topic_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    retrieved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deduped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dedup_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    push_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_push_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    fetch_success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    trace_completeness: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    suggestions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
