from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from copy import deepcopy
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
from app.storage.redis_store import RedisEphemeralStateStore, build_redis_client
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
    run_id: str | None = None
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    queue_message_id: str | None = None
    queue_stream: str | None = None
    retry_reason: str | None = None
    retry_count: int = 0
    max_retries: int | None = None


class RunQueueProtocol(Protocol):
    def enqueue(self, message: RunQueueMessage) -> dict[str, Any]: ...

    def dequeue(self) -> RunQueueMessage | None: ...

    def acknowledge(self, delivery: RunQueueMessage) -> None: ...

    def requeue(self, delivery: RunQueueMessage, *, reason: str) -> None: ...

    def claim_enqueue_slot(self, topic_id: str, trigger: str) -> bool: ...

    def release_enqueue_slot(self, topic_id: str, trigger: str) -> None: ...

    def claim_active_run(self, topic_id: str, run_id: str) -> bool: ...

    def get_active_run(self, topic_id: str) -> str | None: ...

    def release_active_run(self, topic_id: str, run_id: str | None = None) -> None: ...

    def set_retry_state(
        self,
        *,
        run_id: str,
        topic_id: str,
        retry_count: int,
        max_retries: int,
        status: str,
        reason: str | None,
    ) -> dict[str, Any]: ...

    def get_retry_state(self, run_id: str) -> dict[str, Any] | None: ...

    def clear_retry_state(self, run_id: str) -> None: ...


class InMemoryRunQueue:
    def __init__(self) -> None:
        self._queue: deque[RunQueueMessage] = deque()
        self._enqueue_slots: dict[str, tuple[bool, datetime]] = {}
        self._active_runs: dict[str, tuple[str, datetime]] = {}
        self._retry_states: dict[str, tuple[dict[str, Any], datetime]] = {}

    @staticmethod
    def _expires_at(ttl_seconds: int) -> datetime:
        return datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=ttl_seconds)

    @staticmethod
    def _prune_expired(store: dict[str, tuple[Any, datetime]]) -> None:
        now = datetime.now(UTC)
        expired_keys = [key for key, (_, expires_at) in store.items() if expires_at <= now]
        for key in expired_keys:
            del store[key]

    @staticmethod
    def _enqueue_slot_key(topic_id: str, trigger: str) -> str:
        return f"{topic_id}:{trigger}"

    def enqueue(self, message: RunQueueMessage) -> dict[str, Any]:
        self._queue.append(message)
        return {
            "topic_id": message.topic_id,
            "trigger": message.trigger,
            "run_id": message.run_id,
            "status": "queued",
            "enqueued_at": message.enqueued_at,
        }

    def dequeue(self) -> RunQueueMessage | None:
        if not self._queue:
            return None
        return self._queue.popleft()

    def acknowledge(self, delivery: RunQueueMessage) -> None:
        return None

    def requeue(self, delivery: RunQueueMessage, *, reason: str) -> None:
        self.enqueue(
            RunQueueMessage(
                topic_id=delivery.topic_id,
                trigger=delivery.trigger,
                run_id=delivery.run_id,
                retry_reason=reason,
                retry_count=delivery.retry_count + 1,
                max_retries=delivery.max_retries,
            )
        )
        self.acknowledge(delivery)

    def claim_enqueue_slot(
        self,
        topic_id: str,
        trigger: str,
        ttl_seconds: int = 60,
    ) -> bool:
        self._prune_expired(self._enqueue_slots)
        key = self._enqueue_slot_key(topic_id, trigger)
        if key in self._enqueue_slots:
            return False
        self._enqueue_slots[key] = (True, self._expires_at(ttl_seconds))
        return True

    def release_enqueue_slot(self, topic_id: str, trigger: str) -> None:
        self._enqueue_slots.pop(self._enqueue_slot_key(topic_id, trigger), None)

    def claim_active_run(
        self,
        topic_id: str,
        run_id: str,
        ttl_seconds: int = 900,
    ) -> bool:
        self._prune_expired(self._active_runs)
        if topic_id in self._active_runs:
            return False
        self._active_runs[topic_id] = (run_id, self._expires_at(ttl_seconds))
        return True

    def get_active_run(self, topic_id: str) -> str | None:
        self._prune_expired(self._active_runs)
        value = self._active_runs.get(topic_id)
        if value is None:
            return None
        return value[0]

    def release_active_run(self, topic_id: str, run_id: str | None = None) -> None:
        current = self._active_runs.get(topic_id)
        if current is None:
            return
        if run_id is not None and current[0] != run_id:
            return
        del self._active_runs[topic_id]

    def set_retry_state(
        self,
        *,
        run_id: str,
        topic_id: str,
        retry_count: int,
        max_retries: int,
        status: str,
        reason: str | None,
        ttl_seconds: int = 900,
    ) -> dict[str, Any]:
        payload = {
            "run_id": run_id,
            "topic_id": topic_id,
            "retry_count": retry_count,
            "max_retries": max_retries,
            "status": status,
            "reason": reason,
        }
        self._retry_states[run_id] = (payload, self._expires_at(ttl_seconds))
        return dict(payload)

    def get_retry_state(self, run_id: str) -> dict[str, Any] | None:
        self._prune_expired(self._retry_states)
        payload = self._retry_states.get(run_id)
        if payload is None:
            return None
        return dict(payload[0])

    def clear_retry_state(self, run_id: str) -> None:
        self._retry_states.pop(run_id, None)


class RedisStreamRunQueue:
    def __init__(
        self,
        redis_client: Any,
        *,
        stream_key: str = "industry_news_agent:run_stream",
        group_name: str = "monitor-workers",
        consumer_name: str = "monitor-worker-1",
        block_ms: int = 0,
        claim_min_idle_ms: int = 60_000,
        claim_count: int = 1,
    ) -> None:
        self.redis_client = redis_client
        self.state_store = RedisEphemeralStateStore(redis_client)
        self.stream_key = stream_key
        self.group_name = group_name
        self.consumer_name = consumer_name
        self.block_ms = block_ms
        self.claim_min_idle_ms = claim_min_idle_ms
        self.claim_count = claim_count
        self._ensure_group()

    @staticmethod
    def _to_text(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    def _ensure_group(self) -> None:
        try:
            self.redis_client.xgroup_create(
                name=self.stream_key,
                groupname=self.group_name,
                id="0",
                mkstream=True,
            )
        except RedisError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def enqueue(self, message: RunQueueMessage) -> dict[str, Any]:
        payload = {
            "topic_id": message.topic_id,
            "trigger": message.trigger,
            "enqueued_at": message.enqueued_at.isoformat().replace("+00:00", "Z"),
        }
        if message.run_id is not None:
            payload["run_id"] = message.run_id
        if message.retry_reason is not None:
            payload["retry_reason"] = message.retry_reason
        if message.retry_count:
            payload["retry_count"] = str(message.retry_count)
        if message.max_retries is not None:
            payload["max_retries"] = str(message.max_retries)
        message_id = self.redis_client.xadd(self.stream_key, payload)
        return {
            "topic_id": message.topic_id,
            "trigger": message.trigger,
            "status": "queued",
            "enqueued_at": message.enqueued_at,
            "message_id": self._to_text(message_id),
        }

    def _decode_message(
        self,
        stream_name: Any,
        message_id: Any,
        raw_payload: dict[Any, Any],
    ) -> RunQueueMessage:
        payload = {
            self._to_text(key): self._to_text(value)
            for key, value in raw_payload.items()
        }
        return RunQueueMessage(
            topic_id=str(payload["topic_id"]),
            trigger=str(payload["trigger"]),
            run_id=payload.get("run_id"),
            enqueued_at=datetime.fromisoformat(str(payload["enqueued_at"]).replace("Z", "+00:00")),
            queue_message_id=self._to_text(message_id),
            queue_stream=self._to_text(stream_name),
            retry_reason=payload.get("retry_reason"),
            retry_count=int(payload.get("retry_count", "0")),
            max_retries=(
                int(payload["max_retries"]) if payload.get("max_retries") is not None else None
            ),
        )

    def _claim_pending_delivery(self) -> RunQueueMessage | None:
        xautoclaim = getattr(self.redis_client, "xautoclaim", None)
        if xautoclaim is None:
            return None
        claimed = xautoclaim(
            name=self.stream_key,
            groupname=self.group_name,
            consumername=self.consumer_name,
            min_idle_time=self.claim_min_idle_ms,
            start_id="0-0",
            count=self.claim_count,
        )
        if not claimed:
            return None
        if len(claimed) < 2:
            return None
        messages = claimed[1]
        if not messages:
            return None
        message_id, raw_payload = messages[0]
        return self._decode_message(self.stream_key, message_id, raw_payload)

    def dequeue(self) -> RunQueueMessage | None:
        pending_delivery = self._claim_pending_delivery()
        if pending_delivery is not None:
            return pending_delivery

        streams = self.redis_client.xreadgroup(
            groupname=self.group_name,
            consumername=self.consumer_name,
            streams={self.stream_key: ">"},
            count=1,
            block=self.block_ms,
        )
        if not streams:
            return None

        stream_name, messages = streams[0]
        if not messages:
            return None
        message_id, raw_payload = messages[0]
        return self._decode_message(stream_name, message_id, raw_payload)

    def acknowledge(self, delivery: RunQueueMessage) -> None:
        if delivery.queue_message_id is None or delivery.queue_stream is None:
            return None
        self.redis_client.xack(
            delivery.queue_stream,
            self.group_name,
            delivery.queue_message_id.encode("utf-8"),
        )

    def requeue(self, delivery: RunQueueMessage, *, reason: str) -> None:
        requeued_message = RunQueueMessage(
            topic_id=delivery.topic_id,
            trigger=delivery.trigger,
            run_id=delivery.run_id,
            enqueued_at=datetime.now(UTC),
            retry_reason=reason,
            retry_count=delivery.retry_count + 1,
            max_retries=delivery.max_retries,
        )
        self.enqueue(requeued_message)
        self.acknowledge(delivery)

    def claim_enqueue_slot(
        self,
        topic_id: str,
        trigger: str,
        ttl_seconds: int = 60,
    ) -> bool:
        return self.state_store.claim_value(
            key=f"enqueue:{topic_id}:{trigger}",
            value="1",
            ttl_seconds=ttl_seconds,
        )

    def release_enqueue_slot(self, topic_id: str, trigger: str) -> None:
        self.state_store.delete(f"enqueue:{topic_id}:{trigger}")

    def claim_active_run(
        self,
        topic_id: str,
        run_id: str,
        ttl_seconds: int = 900,
    ) -> bool:
        return self.state_store.claim_value(
            key=f"active_run:{topic_id}",
            value=run_id,
            ttl_seconds=ttl_seconds,
        )

    def get_active_run(self, topic_id: str) -> str | None:
        return self.state_store.get_value(f"active_run:{topic_id}")

    def release_active_run(self, topic_id: str, run_id: str | None = None) -> None:
        current = self.get_active_run(topic_id)
        if current is None:
            return
        if run_id is not None and current != run_id:
            return
        self.state_store.delete(f"active_run:{topic_id}")

    def set_retry_state(
        self,
        *,
        run_id: str,
        topic_id: str,
        retry_count: int,
        max_retries: int,
        status: str,
        reason: str | None,
        ttl_seconds: int = 900,
    ) -> dict[str, Any]:
        payload = {
            "run_id": run_id,
            "topic_id": topic_id,
            "retry_count": retry_count,
            "max_retries": max_retries,
            "status": status,
            "reason": reason,
        }
        return self.state_store.set_json(
            key=f"retry:{run_id}",
            payload=payload,
            ttl_seconds=ttl_seconds,
        )

    def get_retry_state(self, run_id: str) -> dict[str, Any] | None:
        return self.state_store.get_json(f"retry:{run_id}")

    def clear_retry_state(self, run_id: str) -> None:
        self.state_store.delete(f"retry:{run_id}")


def build_run_queue(settings: Settings | None = None) -> RunQueueProtocol:
    try:
        redis_client = build_redis_client(settings)
        redis_client.ping()
    except (RedisError, ValidationError):
        return InMemoryRunQueue()
    return RedisStreamRunQueue(redis_client)


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
        self._cancelled_run_ids: set[str] = set()

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

    def _coordination_backend_name(self) -> str:
        if isinstance(self.queue, RedisStreamRunQueue):
            return "redis_stream"
        if isinstance(self.queue, InMemoryRunQueue):
            return "memory"
        return self.queue.__class__.__name__.lower()

    def _release_enqueue_slot(self, topic_id: str, trigger: str) -> None:
        release = getattr(self.queue, "release_enqueue_slot", None)
        if callable(release):
            release(topic_id, trigger)

    def _claim_active_run(self, topic_id: str, run_id: str) -> bool:
        claim = getattr(self.queue, "claim_active_run", None)
        if not callable(claim):
            return True
        return bool(claim(topic_id, run_id))

    def _get_active_run(self, topic_id: str) -> str | None:
        getter = getattr(self.queue, "get_active_run", None)
        if not callable(getter):
            return None
        value = getter(topic_id)
        if value is None:
            return None
        return str(value)

    def _release_active_run(self, topic_id: str, run_id: str | None = None) -> None:
        release = getattr(self.queue, "release_active_run", None)
        if callable(release):
            release(topic_id, run_id)

    def _set_retry_state(
        self,
        *,
        run_id: str,
        topic_id: str,
        retry_count: int,
        max_retries: int,
        status: str,
        reason: str | None,
    ) -> None:
        setter = getattr(self.queue, "set_retry_state", None)
        if callable(setter):
            setter(
                run_id=run_id,
                topic_id=topic_id,
                retry_count=retry_count,
                max_retries=max_retries,
                status=status,
                reason=reason,
            )

    def _clear_retry_state(self, run_id: str) -> None:
        clearer = getattr(self.queue, "clear_retry_state", None)
        if callable(clearer):
            clearer(run_id)

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
            # Coordination backend remains short-lived transport metadata only.
            "coordination_backend": self._coordination_backend_name(),
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
            self._cancelled_run_ids.add(str(initial_state["run_id"]))
            raise TimeoutError(
                f"graph invocation timed out after {self.invocation_timeout_seconds} seconds"
            ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _build_guarded_run_repository(self) -> MonitorRunRepositoryProtocol:
        parent = self
        repository = self.run_repository

        class GuardedRunRepository:
            _blocked_methods = {
                "upsert_monitor_run",
                "create_push_records",
                "upsert_candidate_records",
                "upsert_extracted_item_records",
                "upsert_decision_records",
                "create_run_events",
                "create_eval_result",
            }

            def __getattr__(self, name: str) -> Any:
                target = getattr(repository, name)
                if name not in self._blocked_methods:
                    return target

                def guarded(*args: Any, **kwargs: Any) -> Any:
                    run_id = self._extract_run_id(args, kwargs)
                    if run_id is not None and run_id in parent._cancelled_run_ids:
                        return self._default_result(name)
                    return target(*args, **kwargs)

                return guarded

            @staticmethod
            def _extract_run_id(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str | None:
                if "run_id" in kwargs and kwargs["run_id"] is not None:
                    return str(kwargs["run_id"])
                for arg in args:
                    if hasattr(arg, "run_id"):
                        return str(getattr(arg, "run_id"))
                    if isinstance(arg, tuple) and arg:
                        first = arg[0]
                        if hasattr(first, "run_id"):
                            return str(getattr(first, "run_id"))
                return None

            @staticmethod
            def _default_result(name: str) -> Any:
                if name == "upsert_monitor_run":
                    return None
                if name == "create_eval_result":
                    return None
                return []

        return GuardedRunRepository()  # type: ignore[return-value]

    def _build_graph(self) -> Any:
        settings = _get_optional_settings()
        guarded_run_repository = self._build_guarded_run_repository()
        if settings is None:
            return build_monitor_graph(
                llm=self.llm,
                run_repository=guarded_run_repository,
            )
        return build_monitor_graph(
            llm=self.llm,
            run_repository=guarded_run_repository,
            settings=settings,
        )

    def process_next(self) -> dict[str, Any] | None:
        message = self.queue.dequeue()
        if message is None:
            return None
        self._release_enqueue_slot(message.topic_id, message.trigger)

        topic = self.topic_repository.get_topic(message.topic_id)
        if topic is None:
            self.queue.acknowledge(message)
            return {
                "topic_id": message.topic_id,
                "trigger": message.trigger,
                "status": "missing_topic",
            }
        queue_metrics = self._build_queue_metrics(message)
        active_run = self.run_repository.get_active_run_for_topic(topic.topic_id)
        if active_run is not None:
            if message.retry_reason == "worker_retry" and message.run_id is not None:
                run_id = message.run_id
            elif message.retry_reason == "worker_retry":
                run_id = active_run.run_id
            else:
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
                self.queue.acknowledge(message)
                return {
                    "run_id": active_run.run_id,
                    "topic_id": topic.topic_id,
                    "trigger": message.trigger,
                    "status": "skipped_active_run",
                }
        else:
            run_id = message.run_id or f"run_{uuid.uuid4().hex[:12]}"
        if not self._claim_active_run(topic.topic_id, run_id):
            active_run_id = self._get_active_run(topic.topic_id) or run_id
            self._persist_governance_event(
                run_id=active_run_id,
                topic_id=topic.topic_id,
                event_type="governance_skipped",
                node="worker_active_run_guard",
                message="Skipped queued run because a short-lived coordination lock is already active for the topic.",
                payload={
                    **queue_metrics,
                    "active_run_id": active_run_id,
                },
            )
            self.queue.acknowledge(message)
            return {
                "run_id": active_run_id,
                "topic_id": topic.topic_id,
                "trigger": message.trigger,
                "status": "skipped_active_run",
            }
        base_state = _build_initial_state(topic, run_id)
        base_state["trigger"] = message.trigger
        effective_max_retries = (
            message.max_retries if message.max_retries is not None else self.max_retries
        )
        current_retry_count = message.retry_count
        base_state["retry_count"] = current_retry_count
        base_state["max_retries"] = effective_max_retries
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
        attempt = current_retry_count
        attempt_state = deepcopy(base_state)
        attempt_state["retry_count"] = attempt
        try:
            graph = self._build_graph()
            result = self._invoke_graph_with_timeout(graph, attempt_state)
            self._clear_retry_state(run_id)
            self._release_active_run(topic.topic_id, run_id)
            self.queue.acknowledge(message)
            return {
                "run_id": run_id,
                "topic_id": topic.topic_id,
                "trigger": message.trigger,
                "status": result["status"],
                "retry_count": attempt,
            }
        except Exception as exc:
            last_error = exc
            if attempt >= effective_max_retries:
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
                        "max_retries": effective_max_retries,
                        "error_message": str(exc),
                        **queue_metrics,
                    },
                )
                _mark_run_failed(self.run_repository, attempt_state, exc)
                self._clear_retry_state(run_id)
                self._release_active_run(topic.topic_id, run_id)
                self.queue.acknowledge(message)
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
                    "max_retries": effective_max_retries,
                    "error_message": str(exc),
                    **queue_metrics,
                },
            )
            self._set_retry_state(
                run_id=run_id,
                topic_id=topic.topic_id,
                retry_count=attempt + 1,
                max_retries=effective_max_retries,
                status="queued_for_retry",
                reason=str(exc),
            )
            self.queue.requeue(
                RunQueueMessage(
                    topic_id=message.topic_id,
                    trigger=message.trigger,
                    run_id=run_id,
                    enqueued_at=message.enqueued_at,
                    queue_message_id=message.queue_message_id,
                    queue_stream=message.queue_stream,
                    retry_reason=message.retry_reason,
                    retry_count=attempt,
                    max_retries=effective_max_retries,
                ),
                reason="worker_retry",
            )
            self._release_active_run(topic.topic_id, run_id)
            _persist_initial_run(self.run_repository, attempt_state)
            return {
                "run_id": run_id,
                "topic_id": topic.topic_id,
                "trigger": message.trigger,
                "status": "queued_for_retry",
                "retry_count": attempt,
            }

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
    if not queue.claim_enqueue_slot(topic_id, trigger):
        return {
            "topic_id": topic_id,
            "trigger": trigger,
            "status": "skipped_duplicate",
        }
    return queue.enqueue(
        RunQueueMessage(
            topic_id=topic_id,
            trigger=trigger,
        )
    )
