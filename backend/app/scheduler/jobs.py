from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.scheduler.worker import RunQueueProtocol, enqueue_topic_run


class SchedulerProtocol(Protocol):
    def add_job(self, *args: Any, **kwargs: Any) -> Any: ...

    def get_job(self, job_id: str) -> Any: ...

    def remove_job(self, job_id: str) -> None: ...

    def start(self, paused: bool = False) -> None: ...

    def shutdown(self, wait: bool = True) -> None: ...


@dataclass(slots=True)
class TopicSchedulerService:
    scheduler: SchedulerProtocol
    queue: RunQueueProtocol

    def register_topic(self, *, topic_id: str, schedule_cron: str | None, enabled: bool) -> None:
        job_id = self._job_id(topic_id)
        existing = self.scheduler.get_job(job_id)
        if existing is not None:
            self.scheduler.remove_job(job_id)

        if not enabled or not schedule_cron:
            return

        self.scheduler.add_job(
            enqueue_topic_run,
            trigger=CronTrigger.from_crontab(schedule_cron),
            id=job_id,
            kwargs={
                "topic_id": topic_id,
                "queue": self.queue,
                "trigger": "scheduler",
            },
            replace_existing=True,
        )

    def rehydrate_topics(self, topics: list[Any]) -> None:
        for topic in topics:
            self.register_topic(
                topic_id=str(topic.topic_id),
                schedule_cron=topic.schedule_cron,
                enabled=bool(topic.enabled),
            )

    @staticmethod
    def _job_id(topic_id: str) -> str:
        return f"topic:{topic_id}"


def build_scheduler() -> BackgroundScheduler:
    return BackgroundScheduler()
