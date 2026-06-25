from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class CandidateTaskOrchestrator:
    def __init__(
        self,
        *,
        fetch_concurrency: int = 2,
        extract_concurrency: int = 2,
        evaluate_concurrency: int = 2,
    ) -> None:
        self.fetch_concurrency = fetch_concurrency
        self.extract_concurrency = extract_concurrency
        self.evaluate_concurrency = evaluate_concurrency

    def build_initial_tasks(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        run_id = str(state["run_id"])
        candidate_pool = list(state.get("retrieval_output", {}).get("candidate_pool", []))
        tasks: list[dict[str, Any]] = []
        for candidate in candidate_pool:
            candidate_id = str(candidate["candidate_id"])
            tasks.append(
                {
                    "task_id": f"{run_id}:fetch:{candidate_id}",
                    "run_id": run_id,
                    "candidate_id": candidate_id,
                    "stage": "fetch",
                    "status": "ready",
                    "attempt": 1,
                    "max_attempts": 2,
                    "depends_on_task_ids": [],
                    "input_ref": {"candidate_id": candidate_id},
                    "output_ref": {},
                    "error_code": None,
                    "error_message": None,
                    "started_at": None,
                    "finished_at": None,
                }
            )
        return tasks

    def build_follow_up_tasks(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        if task.get("status") != "completed":
            return []

        run_id = str(task["run_id"])
        candidate_id = str(task["candidate_id"])
        stage = str(task["stage"])
        if stage == "fetch":
            next_stage = "extract"
        elif stage == "extract":
            next_stage = "evaluate"
        else:
            return []

        return [
            {
                "task_id": f"{run_id}:{next_stage}:{candidate_id}",
                "run_id": run_id,
                "candidate_id": candidate_id,
                "stage": next_stage,
                "status": "ready",
                "attempt": 1,
                "max_attempts": 2,
                "depends_on_task_ids": [str(task["task_id"])],
                "input_ref": {"candidate_id": candidate_id},
                "output_ref": {},
                "error_code": None,
                "error_message": None,
                "started_at": None,
                "finished_at": None,
            }
        ]

    def concurrency_limit_for_stage(self, stage: str) -> int:
        if stage == "fetch":
            return self.fetch_concurrency
        if stage == "extract":
            return self.extract_concurrency
        return self.evaluate_concurrency

    def mark_task_in_progress(self, task: dict[str, Any]) -> dict[str, Any]:
        started = dict(task)
        started["status"] = "in_progress"
        started["started_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return started

    def mark_task_completed(
        self,
        task: dict[str, Any],
        *,
        output_ref: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        completed = dict(task)
        completed["status"] = "completed"
        completed["output_ref"] = dict(output_ref or {})
        completed["started_at"] = task.get("started_at")
        completed["finished_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return completed

    def mark_task_failed(
        self,
        task: dict[str, Any],
        *,
        error_code: str,
        error_message: str,
    ) -> dict[str, Any]:
        failed = dict(task)
        failed["status"] = "failed"
        failed["error_code"] = error_code
        failed["error_message"] = error_message
        failed["started_at"] = task.get("started_at")
        failed["finished_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return failed

    def build_retry_task(self, task: dict[str, Any]) -> dict[str, Any] | None:
        attempt = int(task.get("attempt", 1))
        max_attempts = int(task.get("max_attempts", 1))
        if attempt >= max_attempts:
            return None
        retried = dict(task)
        retried["status"] = "ready"
        retried["attempt"] = attempt + 1
        retried["error_code"] = None
        retried["error_message"] = None
        retried["started_at"] = None
        retried["finished_at"] = None
        retried["output_ref"] = {}
        return retried

    def build_runtime_view(self, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "ready_count": sum(1 for task in tasks if task.get("status") == "ready"),
            "in_progress_count": sum(
                1 for task in tasks if task.get("status") == "in_progress"
            ),
            "completed_count": sum(
                1 for task in tasks if task.get("status") == "completed"
            ),
            "failed_count": sum(1 for task in tasks if task.get("status") == "failed"),
            "skipped_count": sum(1 for task in tasks if task.get("status") == "skipped"),
            "stage_slots": {
                "fetch": {
                    "limit": self.fetch_concurrency,
                    "in_progress": sum(
                        1
                        for task in tasks
                        if task.get("stage") == "fetch"
                        and task.get("status") == "in_progress"
                    ),
                },
                "extract": {
                    "limit": self.extract_concurrency,
                    "in_progress": sum(
                        1
                        for task in tasks
                        if task.get("stage") == "extract"
                        and task.get("status") == "in_progress"
                    ),
                },
                "evaluate": {
                    "limit": self.evaluate_concurrency,
                    "in_progress": sum(
                        1
                        for task in tasks
                        if task.get("stage") == "evaluate"
                        and task.get("status") == "in_progress"
                    ),
                },
            },
        }

    def build_summary(self, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        failed_logical_tasks = {
            (str(task.get("stage", "")), str(task.get("candidate_id", "")))
            for task in tasks
            if task.get("status") == "failed"
        }
        return {
            "task_count": len(tasks),
            "completed_count": sum(
                1 for task in tasks if task.get("status") == "completed"
            ),
            "failed_count": len(failed_logical_tasks),
            "skipped_count": sum(1 for task in tasks if task.get("status") == "skipped"),
            "fetch_completed_count": sum(
                1
                for task in tasks
                if task.get("stage") == "fetch"
                and task.get("status") == "completed"
            ),
            "extract_completed_count": sum(
                1
                for task in tasks
                if task.get("stage") == "extract"
                and task.get("status") == "completed"
            ),
            "evaluate_completed_count": sum(
                1
                for task in tasks
                if task.get("stage") == "evaluate"
                and task.get("status") == "completed"
            ),
        }
