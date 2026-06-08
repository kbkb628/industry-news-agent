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
