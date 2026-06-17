from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from copy import deepcopy
import json
from threading import Event
import uuid
from typing import Any, Protocol

from app.agent.graph import build_monitor_graph
from app.api.monitor import (
    _build_initial_state,
    _get_optional_settings,
    _mark_run_failed,
    _persist_initial_run,
)
from app.core.config import Settings
from app.llm.base import BaseLLMClient
from app.llm.mock_client import MockLLM
from app.storage.redis_store import build_redis_client
from app.storage.repository import (
    MonitorRunRepositoryProtocol,
    RunEventCreateData,
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
        max_retries: int = 1,
        invocation_timeout_seconds: float = 30.0,
    ) -> None:
        self.topic_repository = topic_repository
        self.run_repository = run_repository
        self.llm = llm or MockLLM()
        self.queue = queue
        self.max_retries = max_retries
        self.invocation_timeout_seconds = invocation_timeout_seconds

    @staticmethod
    def _serialize_payload_value(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat().replace("+00:00", "Z")
        if isinstance(value, dict):
            return {
                str(key): MonitorWorkerService._serialize_payload_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [MonitorWorkerService._serialize_payload_value(item) for item in value]
        if isinstance(value, tuple):
            return [MonitorWorkerService._serialize_payload_value(item) for item in value]
        return value

    def _build_queue_metrics(self, message: RunQueueMessage) -> dict[str, Any]:
        dequeued_at = datetime.now(UTC)
        queue_wait_ms = max(
            0,
            int((dequeued_at - message.enqueued_at).total_seconds() * 1000),
        )
        return {
            "trigger": message.trigger,
            "enqueued_at": message.enqueued_at,
            "dequeued_at": dequeued_at,
            "queue_wait_ms": queue_wait_ms,
        }

    def _persist_governance_event(
        self,
        *,
        run_id: str,
        topic_id: str,
        event_type: str,
        node: str,
        message: str,
        payload: dict[str, Any],
    ) -> None:
        self.run_repository.create_run_events(
            (
                RunEventCreateData(
                    run_id=run_id,
                    topic_id=topic_id,
                    event_type=event_type,
                    node=node,
                    message=message,
                    payload=self._serialize_payload_value(payload),
                    elapsed_ms=None,
                ),
            )
        )

    def _invoke_graph_with_timeout(
        self,
        graph: Any,
        initial_state: dict[str, Any],
    ) -> dict[str, Any]:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="monitor-graph")
        future = executor.submit(graph.invoke, deepcopy(initial_state))
        try:
            return future.result(timeout=self.invocation_timeout_seconds)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise TimeoutError(
                f"graph invocation timed out after {self.invocation_timeout_seconds} seconds"
            ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _build_graph(self) -> Any:
        settings = _get_optional_settings()
        if settings is None:
            return build_monitor_graph(
                llm=self.llm,
                run_repository=self.run_repository,
            )
        return build_monitor_graph(
            llm=self.llm,
            run_repository=self.run_repository,
            settings=settings,
        )

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
        queue_metrics = self._build_queue_metrics(message)
        active_run = self.run_repository.get_active_run_for_topic(topic.topic_id)
        if active_run is not None:
            self._persist_governance_event(
                run_id=active_run.run_id,
                topic_id=topic.topic_id,
                event_type="governance_skipped",
                node="worker_active_run_guard",
                message="Skipped queued run because a monitor run is already active for the topic.",
                payload={
                    **queue_metrics,
                    "active_run_id": active_run.run_id,
                },
            )
            return {
                "run_id": active_run.run_id,
                "topic_id": topic.topic_id,
                "trigger": message.trigger,
                "status": "skipped_active_run",
            }

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        base_state = _build_initial_state(topic, run_id)
        base_state["trigger"] = message.trigger
        base_state["retry_count"] = 0
        base_state["max_retries"] = self.max_retries
        _persist_initial_run(self.run_repository, base_state)
        self._persist_governance_event(
            run_id=run_id,
            topic_id=topic.topic_id,
            event_type="queue_dequeued",
            node="worker_dequeue",
            message="Dequeued queued monitor run for worker execution.",
            payload=queue_metrics,
        )

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            attempt_state = deepcopy(base_state)
            attempt_state["retry_count"] = attempt
            try:
                graph = self._build_graph()
                result = self._invoke_graph_with_timeout(graph, attempt_state)
                return {
                    "run_id": run_id,
                    "topic_id": topic.topic_id,
                    "trigger": message.trigger,
                    "status": result["status"],
                    "retry_count": attempt,
                }
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    attempt_state["retry_count"] = attempt + 1
                    failure_node = (
                        "worker_timeout" if isinstance(exc, TimeoutError) else "worker_failed"
                    )
                    failure_event_type = (
                        "governance_timeout"
                        if isinstance(exc, TimeoutError)
                        else "governance_failed"
                    )
                    self._persist_governance_event(
                        run_id=run_id,
                        topic_id=topic.topic_id,
                        event_type=failure_event_type,
                        node=failure_node,
                        message=(
                            "Worker invocation timed out and the queued run was marked failed."
                            if isinstance(exc, TimeoutError)
                            else "Worker invocation failed and the queued run was marked failed."
                        ),
                        payload={
                            "attempt": attempt + 1,
                            "max_retries": self.max_retries,
                            "error_message": str(exc),
                            **queue_metrics,
                        },
                    )
                    _mark_run_failed(self.run_repository, attempt_state, exc)
                    return {
                        "run_id": run_id,
                        "topic_id": topic.topic_id,
                        "trigger": message.trigger,
                        "status": "failed",
                        "retry_count": attempt,
                    }
                self._persist_governance_event(
                    run_id=run_id,
                    topic_id=topic.topic_id,
                    event_type="governance_retry",
                    node="worker_retry",
                    message="Worker invocation failed and will be retried.",
                    payload={
                        "attempt": attempt + 1,
                        "max_retries": self.max_retries,
                        "error_message": str(exc),
                        **queue_metrics,
                    },
                )
                _persist_initial_run(self.run_repository, attempt_state)

        if last_error is not None:
            raise last_error
        return None


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
