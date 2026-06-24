from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.storage.database import Base, build_engine, build_session_factory
from app.storage.repository import build_monitor_run_repository, build_topic_repository


def _build_demo_session_factory(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'demo_bootstrap.db'}"
    settings = Settings(
        database_url=database_url,
        redis_url="redis://localhost:6379/0",
    )
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    return settings, engine, build_session_factory(engine)


def test_demo_bootstrap_persists_full_demo_evidence_chain(tmp_path: Path) -> None:
    from app.demo.bootstrap import bootstrap_demo_run

    settings, engine, session_factory = _build_demo_session_factory(tmp_path)
    try:
        result = bootstrap_demo_run(
            session_factory=session_factory,
            settings=settings,
        )

        with session_factory() as session:
            topic_repository = build_topic_repository(session)
            run_repository = build_monitor_run_repository(session)
            topic = topic_repository.get_topic(result.topic_id)
            run = run_repository.get_monitor_run(result.run_id)
            candidates = run_repository.list_candidate_records(result.run_id)
            extracted_items = run_repository.list_extracted_item_records(result.run_id)
            decision_records = run_repository.list_decision_records(result.run_id)
            push_records = run_repository.list_push_records(run_id=result.run_id)
            candidate_tasks = run_repository.list_candidate_task_records(result.run_id)
            events = run_repository.list_run_events(result.run_id)
            eval_result = run_repository.get_eval_result(result.run_id)

        assert topic is not None
        assert run is not None
        assert run.status == "completed"
        assert result.candidate_count == len(candidates)
        assert result.candidate_count >= 3
        assert len(extracted_items) >= 3
        assert len(decision_records) >= 2
        assert result.push_count == len(push_records) == 1
        assert result.event_count == len(events)
        assert result.candidate_task_count == len(candidate_tasks)
        assert result.candidate_task_count >= 9
        assert run.state_snapshot["candidate_task_summary"]["task_count"] >= 9
        assert len(run.state_snapshot["final_decisions"]) >= 2
        assert eval_result is not None
        assert eval_result["run_id"] == result.run_id
        assert eval_result["push_count"] == 1
        assert any(
            event["event_type"] == "notification_skipped" for event in events
        )
    finally:
        engine.dispose()


def test_demo_bootstrap_evidence_is_visible_through_existing_apis(
    tmp_path: Path,
    sqlalchemy_client_factory,
) -> None:
    from app.demo.bootstrap import bootstrap_demo_run

    settings, engine, session_factory = _build_demo_session_factory(tmp_path)
    try:
        result = bootstrap_demo_run(
            session_factory=session_factory,
            settings=settings,
        )

        with sqlalchemy_client_factory(session_factory) as client:
            topics_response = client.get("/api/topics")
            run_response = client.get(f"/api/monitor/runs/{result.run_id}")
            tasks_response = client.get(
                f"/api/monitor/runs/{result.run_id}/candidate-tasks"
            )
            events_response = client.get(
                f"/api/monitor/runs/{result.run_id}/events"
            )
            pushes_response = client.get("/api/pushes")
            quality_response = client.get("/api/eval/summary")

        assert topics_response.status_code == 200
        assert any(
            topic["topic_id"] == result.topic_id
            for topic in topics_response.json()
        )

        assert run_response.status_code == 200
        assert run_response.json()["run_id"] == result.run_id
        assert run_response.json()["status"] == "completed"
        assert run_response.json()["candidate_task_summary"]["task_count"] >= 9
        assert len(run_response.json()["final_decisions"]) >= 2

        assert tasks_response.status_code == 200
        assert len(tasks_response.json()["items"]) >= 9

        assert events_response.status_code == 200
        assert any(
            event["event_type"] == "notification_skipped"
            for event in events_response.json()["events"]
        )

        assert pushes_response.status_code == 200
        assert any(
            push["run_id"] == result.run_id
            for push in pushes_response.json()["pushes"]
        )

        assert quality_response.status_code == 200
        assert quality_response.json()["latest_eval"]["run_id"] == result.run_id
        assert quality_response.json()["latest_eval"]["push_count"] == 1
    finally:
        engine.dispose()


def test_demo_bootstrap_initializes_schema_for_fresh_database(tmp_path: Path) -> None:
    from app.demo.bootstrap import bootstrap_demo_run

    database_url = f"sqlite+pysqlite:///{tmp_path / 'fresh_demo_bootstrap.db'}"
    settings = Settings(
        database_url=database_url,
        redis_url="redis://localhost:6379/0",
    )
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    try:
        result = bootstrap_demo_run(
            session_factory=session_factory,
            settings=settings,
        )

        with session_factory() as session:
            run_repository = build_monitor_run_repository(session)
            run = run_repository.get_monitor_run(result.run_id)

        assert run is not None
        assert run.status == "completed"
    finally:
        engine.dispose()
