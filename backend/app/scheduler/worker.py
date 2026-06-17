from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from threading import Event
import time
import uuid
from typing import Any, Protocol

from app.agent.graph import build_monitor_graph
from app.api.monitor import _build_initial_state, _mark_run_failed, _persist_initial_run
from app.core.config import Settings
from app.llm.base import BaseLLMClient
from app.llm.mock_client import MockLLM
from app.storage.redis_store import build_redis_client
from app.storage.repository import (
    MonitorRunRepositoryProtocol,
    TopicRepositoryProtocol,
    build_monitor_run_repository,
    build_topic_repository,
)
from pydantic import ValidationError
from redis import RedisError
from sqlalchemy.orm import sessionmaker


@dataclass(frozen=True, slots=True)
class RunQueueMessage:
    topic_id: str
    trigger: str
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class RunQueueProtocol(Protocol):
    def enqueue(self, message: RunQueueMessage) -> dict[str, Any]: ...

    def dequeue(self) -> RunQueueMessage | None: ...


class InMemoryRunQueue:
    def __init__(self) -> None:
        self._queue: deque[RunQueueMessage] = deque()

    def enqueue(self, message: RunQueueMessage) -> dict[str, Any]:
        self._queue.append(message)
        return {
            "topic_id": message.topic_id,
            "trigger": message.trigger,
            "status": "queued",
            "enqueued_at": message.enqueued_at,
        }

    def dequeue(self) -> RunQueueMessage | None:
        if not self._queue:
            return None
        return self._queue.popleft()


class RedisRunQueue:
    def __init__(self, redis_client: Any, *, queue_key: str = "industry_news_agent:run_queue") -> None:
        self.redis_client = redis_client
        self.queue_key = queue_key

    def enqueue(self, message: RunQueueMessage) -> dict[str, Any]:
        payload = {
            "topic_id": message.topic_id,
            "trigger": message.trigger,
            "enqueued_at": message.enqueued_at.isoformat().replace("+00:00", "Z"),
        }
        self.redis_client.rpush(self.queue_key, json.dumps(payload))
        return {
            "topic_id": message.topic_id,
            "trigger": message.trigger,
            "status": "queued",
            "enqueued_at": message.enqueued_at,
        }

    def dequeue(self) -> RunQueueMessage | None:
        raw_payload = self.redis_client.lpop(self.queue_key)
        if raw_payload is None:
            return None

        payload = json.loads(raw_payload)
        return RunQueueMessage(
            topic_id=str(payload["topic_id"]),
            trigger=str(payload["trigger"]),
            enqueued_at=datetime.fromisoformat(str(payload["enqueued_at"]).replace("Z", "+00:00")),
        )


def build_run_queue(settings: Settings | None = None) -> RunQueueProtocol:
    try:
        redis_client = build_redis_client(settings)
        redis_client.ping()
    except (RedisError, ValidationError):
        return InMemoryRunQueue()
    return RedisRunQueue(redis_client)


class MonitorWorkerService:
    def __init__(
        self,
        *,
        topic_repository: TopicRepositoryProtocol,
        run_repository: MonitorRunRepositoryProtocol,
        llm: BaseLLMClient | None = None,
        queue: RunQueueProtocol,
    ) -> None:
        self.topic_repository = topic_repository
        self.run_repository = run_repository
        self.llm = llm or MockLLM()
        self.queue = queue

    def process_next(self) -> dict[str, Any] | None:
        message = self.queue.dequeue()
        if message is None:
            return None

        topic = self.topic_repository.get_topic(message.topic_id)
        if topic is None:
            return {
                "topic_id": message.topic_id,
                "trigger": message.trigger,
                "status": "missing_topic",
            }

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        initial_state = _build_initial_state(topic, run_id)
        initial_state["trigger"] = message.trigger
        _persist_initial_run(self.run_repository, initial_state)

        graph = build_monitor_graph(llm=self.llm, run_repository=self.run_repository)
        try:
            result = graph.invoke(initial_state)
        except Exception as exc:
            _mark_run_failed(self.run_repository, initial_state, exc)
            return {
                "run_id": run_id,
                "topic_id": topic.topic_id,
                "trigger": message.trigger,
                "status": "failed",
            }

        return {
            "run_id": run_id,
            "topic_id": topic.topic_id,
            "trigger": message.trigger,
            "status": result["status"],
        }


class MonitorWorkerLoop:
    def __init__(
        self,
        *,
        queue: RunQueueProtocol,
        session_factory: sessionmaker[Any],
        poll_interval_seconds: float = 0.2,
        llm: BaseLLMClient | None = None,
    ) -> None:
        self.queue = queue
        self.session_factory = session_factory
        self.poll_interval_seconds = poll_interval_seconds
        self.llm = llm or MockLLM()

    def run_forever(self, stop_event: Event) -> None:
        while not stop_event.is_set():
            try:
                processed = self.process_next()
            except Exception:
                processed = None
            if processed is None:
                stop_event.wait(self.poll_interval_seconds)

    def process_next(self) -> dict[str, Any] | None:
        session = self.session_factory()
        try:
            worker = MonitorWorkerService(
                topic_repository=build_topic_repository(session),
                run_repository=build_monitor_run_repository(session),
                llm=self.llm,
                queue=self.queue,
            )
            return worker.process_next()
        finally:
            session.close()


def enqueue_topic_run(
    topic_id: str,
    *,
    queue: RunQueueProtocol,
    trigger: str = "scheduler",
) -> dict[str, Any]:
    return queue.enqueue(
        RunQueueMessage(
            topic_id=topic_id,
            trigger=trigger,
        )
    )
