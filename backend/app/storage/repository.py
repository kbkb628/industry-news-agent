from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import EvalResult, MonitorRun, PushRecord, RunEvent, Topic


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


@dataclass(frozen=True, slots=True)
class MonitorRunUpsertData:
    run_id: str
    topic_id: str
    status: str
    state_snapshot: dict[str, Any]
    error_summary: str | None
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class MonitorRunRecord:
    run_id: str
    topic_id: str
    status: str
    state_snapshot: dict[str, Any]
    error_summary: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PushRecordCreateData:
    run_id: str
    topic_id: str
    candidate_id: str
    extracted_id: str | None
    title: str
    url: str
    summary: str | None
    should_push: bool
    score: float
    decision_reason: str | None
    pushed_at: datetime | None


@dataclass(frozen=True, slots=True)
class RunEventCreateData:
    run_id: str
    topic_id: str
    event_type: str
    node: str
    message: str
    payload: dict[str, Any]
    elapsed_ms: int | None


@dataclass(frozen=True, slots=True)
class EvalResultCreateData:
    run_id: str
    topic_id: str
    retrieved_count: int
    deduped_count: int
    dedup_rate: float
    push_count: int
    duplicate_push_count: int
    tool_success_rate: float
    fetch_success_rate: float
    trace_completeness: float
    suggestions: tuple[str, ...]


class MonitorRunRepositoryProtocol(Protocol):
    def upsert_monitor_run(self, payload: MonitorRunUpsertData) -> MonitorRunRecord: ...

    def get_monitor_run(self, run_id: str) -> MonitorRunRecord | None: ...

    def get_active_run_for_topic(self, topic_id: str) -> MonitorRunRecord | None: ...

    def list_push_history(self, topic_id: str) -> list[dict[str, Any]]: ...

    def list_push_records(
        self,
        *,
        topic_id: str | None = None,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def create_push_records(
        self,
        payloads: tuple[PushRecordCreateData, ...],
    ) -> list[dict[str, Any]]: ...

    def list_run_events(self, run_id: str) -> list[dict[str, Any]]: ...

    def create_run_events(
        self,
        payloads: tuple[RunEventCreateData, ...],
    ) -> list[dict[str, Any]]: ...

    def get_eval_result(self, run_id: str | None = None) -> dict[str, Any] | None: ...

    def create_eval_result(self, payload: EvalResultCreateData) -> dict[str, Any]: ...


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


def _to_monitor_run_record(model: MonitorRun) -> MonitorRunRecord:
    return MonitorRunRecord(
        run_id=model.run_id,
        topic_id=model.topic_id,
        status=model.status,
        state_snapshot=dict(model.state_snapshot),
        error_summary=model.error_summary,
        started_at=model.started_at,
        finished_at=model.finished_at,
        created_at=model.created_at,
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


class UnimplementedMonitorRunRepository:
    def __init__(self, session: Session | None = None) -> None:
        self.session = session

    def upsert_monitor_run(self, payload: MonitorRunUpsertData) -> MonitorRunRecord:
        raise NotImplementedError(
            "Monitor run persistence is deferred until a database session is provided."
        )

    def get_monitor_run(self, run_id: str) -> MonitorRunRecord | None:
        raise NotImplementedError(
            "Monitor run queries are deferred until a database session is provided."
        )

    def get_active_run_for_topic(self, topic_id: str) -> MonitorRunRecord | None:
        raise NotImplementedError(
            "Active run queries are deferred until a database session is provided."
        )

    def list_push_history(self, topic_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "Push history persistence is deferred until a database session is provided."
        )

    def list_push_records(
        self,
        *,
        topic_id: str | None = None,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "Push record queries are deferred until a database session is provided."
        )

    def create_push_records(
        self,
        payloads: tuple[PushRecordCreateData, ...],
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "Push record persistence is deferred until a database session is provided."
        )

    def list_run_events(self, run_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "Event queries are deferred until a database session is provided."
        )

    def create_run_events(
        self,
        payloads: tuple[RunEventCreateData, ...],
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "Event persistence is deferred until a database session is provided."
        )

    def get_eval_result(self, run_id: str | None = None) -> dict[str, Any] | None:
        raise NotImplementedError(
            "Eval queries are deferred until a database session is provided."
        )

    def create_eval_result(self, payload: EvalResultCreateData) -> dict[str, Any]:
        raise NotImplementedError(
            "Eval result persistence is deferred until a database session is provided."
        )


class SqlAlchemyMonitorRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _commit(self) -> None:
        try:
            self.session.commit()
        except SQLAlchemyError:
            self.session.rollback()
            raise

    def upsert_monitor_run(self, payload: MonitorRunUpsertData) -> MonitorRunRecord:
        current_time = datetime.now(UTC)
        monitor_run = self.session.get(MonitorRun, payload.run_id)
        if monitor_run is None:
            monitor_run = MonitorRun(
                run_id=payload.run_id,
                topic_id=payload.topic_id,
                status=payload.status,
                state_snapshot=dict(payload.state_snapshot),
                error_summary=payload.error_summary,
                started_at=payload.started_at or current_time,
                finished_at=payload.finished_at,
            )
            self.session.add(monitor_run)
        else:
            monitor_run.topic_id = payload.topic_id
            monitor_run.status = payload.status
            monitor_run.state_snapshot = dict(payload.state_snapshot)
            monitor_run.error_summary = payload.error_summary
            if payload.started_at is not None:
                monitor_run.started_at = payload.started_at
            if payload.finished_at is not None:
                monitor_run.finished_at = payload.finished_at
            elif payload.status == "completed" and monitor_run.finished_at is None:
                monitor_run.finished_at = current_time

        self._commit()
        self.session.refresh(monitor_run)
        return _to_monitor_run_record(monitor_run)

    def get_monitor_run(self, run_id: str) -> MonitorRunRecord | None:
        monitor_run = self.session.get(MonitorRun, run_id)
        if monitor_run is None:
            return None
        return _to_monitor_run_record(monitor_run)

    def get_active_run_for_topic(self, topic_id: str) -> MonitorRunRecord | None:
        monitor_run = self.session.scalars(
            select(MonitorRun)
            .where(MonitorRun.topic_id == topic_id)
            .where(MonitorRun.status == "running")
            .order_by(MonitorRun.created_at.desc(), MonitorRun.run_id.desc())
        ).first()
        if monitor_run is None:
            return None
        return _to_monitor_run_record(monitor_run)

    def list_push_history(self, topic_id: str) -> list[dict[str, Any]]:
        history = self.session.scalars(
            select(PushRecord)
            .where(PushRecord.topic_id == topic_id)
            .where(PushRecord.should_push.is_(True))
            .order_by(PushRecord.pushed_at.desc(), PushRecord.created_at.desc())
        ).all()
        return [self._serialize_push_record(record) for record in history]

    def list_push_records(
        self,
        *,
        topic_id: str | None = None,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        statement = select(PushRecord)
        if topic_id is not None:
            statement = statement.where(PushRecord.topic_id == topic_id)
        if run_id is not None:
            statement = statement.where(PushRecord.run_id == run_id)
        records = self.session.scalars(
            statement.order_by(PushRecord.created_at.desc(), PushRecord.push_id.desc())
        ).all()
        return [self._serialize_push_record(record) for record in records]

    def create_push_records(
        self,
        payloads: tuple[PushRecordCreateData, ...],
    ) -> list[dict[str, Any]]:
        models: list[PushRecord] = []
        for payload in payloads:
            model = PushRecord(
                run_id=payload.run_id,
                topic_id=payload.topic_id,
                candidate_id=payload.candidate_id,
                extracted_id=payload.extracted_id,
                title=payload.title,
                url=payload.url,
                summary=payload.summary,
                should_push=payload.should_push,
                score=payload.score,
                decision_reason=payload.decision_reason,
                pushed_at=payload.pushed_at,
            )
            self.session.add(model)
            models.append(model)

        self._commit()
        for model in models:
            self.session.refresh(model)
        return [self._serialize_push_record(model) for model in models]

    def _serialize_push_record(self, record: PushRecord) -> dict[str, Any]:
        return {
            "push_id": record.push_id,
            "run_id": record.run_id,
            "topic_id": record.topic_id,
            "candidate_id": record.candidate_id,
            "extracted_id": record.extracted_id,
            "title": record.title,
            "url": record.url,
            "summary": record.summary,
            "should_push": record.should_push,
            "score": record.score,
            "decision_reason": record.decision_reason,
            "pushed_at": record.pushed_at,
        }

    def list_run_events(self, run_id: str) -> list[dict[str, Any]]:
        models = self.session.scalars(
            select(RunEvent)
            .where(RunEvent.run_id == run_id)
            .order_by(RunEvent.created_at.asc(), RunEvent.event_id.asc())
        ).all()
        return [self._serialize_run_event(model) for model in models]

    def create_run_events(
        self,
        payloads: tuple[RunEventCreateData, ...],
    ) -> list[dict[str, Any]]:
        models: list[RunEvent] = []
        for payload in payloads:
            model = RunEvent(
                run_id=payload.run_id,
                topic_id=payload.topic_id,
                event_type=payload.event_type,
                node=payload.node,
                message=payload.message,
                payload=dict(payload.payload),
                elapsed_ms=payload.elapsed_ms,
            )
            self.session.add(model)
            models.append(model)

        self._commit()
        for model in models:
            self.session.refresh(model)
        return [self._serialize_run_event(model) for model in models]

    def _serialize_run_event(self, event: RunEvent) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "run_id": event.run_id,
            "topic_id": event.topic_id,
            "event_type": event.event_type,
            "node": event.node,
            "message": event.message,
            "payload": dict(event.payload),
            "elapsed_ms": event.elapsed_ms,
            "created_at": event.created_at,
        }

    def get_eval_result(self, run_id: str | None = None) -> dict[str, Any] | None:
        statement = select(EvalResult)
        if run_id is not None:
            statement = statement.where(EvalResult.run_id == run_id)
        model = self.session.scalars(
            statement.order_by(EvalResult.created_at.desc(), EvalResult.eval_id.desc())
        ).first()
        if model is None:
            return None
        return self._serialize_eval_result(model)

    def create_eval_result(self, payload: EvalResultCreateData) -> dict[str, Any]:
        model = EvalResult(
            run_id=payload.run_id,
            topic_id=payload.topic_id,
            retrieved_count=payload.retrieved_count,
            deduped_count=payload.deduped_count,
            dedup_rate=payload.dedup_rate,
            push_count=payload.push_count,
            duplicate_push_count=payload.duplicate_push_count,
            tool_success_rate=payload.tool_success_rate,
            fetch_success_rate=payload.fetch_success_rate,
            trace_completeness=payload.trace_completeness,
            suggestions=list(payload.suggestions),
        )
        self.session.add(model)
        self._commit()
        self.session.refresh(model)
        return self._serialize_eval_result(model)

    def _serialize_eval_result(self, model: EvalResult) -> dict[str, Any]:
        return {
            "eval_id": model.eval_id,
            "run_id": model.run_id,
            "topic_id": model.topic_id,
            "retrieved_count": model.retrieved_count,
            "deduped_count": model.deduped_count,
            "dedup_rate": model.dedup_rate,
            "push_count": model.push_count,
            "duplicate_push_count": model.duplicate_push_count,
            "tool_success_rate": model.tool_success_rate,
            "fetch_success_rate": model.fetch_success_rate,
            "trace_completeness": model.trace_completeness,
            "suggestions": list(model.suggestions),
            "created_at": model.created_at,
        }


def build_monitor_run_repository(
    session: Session | None = None,
) -> MonitorRunRepositoryProtocol:
    if session is None:
        return UnimplementedMonitorRunRepository(session=session)
    return SqlAlchemyMonitorRunRepository(session=session)
