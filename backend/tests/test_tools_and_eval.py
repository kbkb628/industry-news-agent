import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock, Thread
import time

import pytest
from pydantic import ValidationError
from redis import RedisError

import app.rag.keyword_retriever as keyword_retriever_module
from app.llm.base import ArticleExtractionResult, CandidateScoreResult
from app.llm.mock_client import MockLLM
from app.mcp.local_gateway import LocalToolGateway
from app.rag.keyword_retriever import KeywordRetriever
from app.rag.knowledge_loader import (
    DEFAULT_KNOWLEDGE_BASE_PATH,
    KnowledgeDocument,
    load_knowledge_base,
)
from app.rag.bm25_retriever import BM25Retriever
from app.rag.hybrid_retriever import retrieve_hybrid_context
from app.rag.local_vector_retriever import LocalVectorRetriever
from app.tools.responses import ToolResponse

from app.core.config import Settings, get_settings
from app.eval.judge import (
    OpenAICompatibleEvalJudge,
    build_eval_judge,
    MockEvalJudge,
)
from app.eval.rule_scorer import score_run
from app.scheduler.worker import (
    InMemoryRunQueue,
    RedisStreamRunQueue,
    RunQueueMessage,
    build_run_queue,
)
from app.storage.database import (
    Base,
    build_engine,
    build_session_factory,
    get_engine,
    get_session_factory,
    reset_engine_registry,
)
from app.storage.models import (
    CandidateRecord,
    DecisionRecord,
    EvalResult,
    ExtractedItemRecord,
    Topic,
)
from app.storage.repository import (
    CandidateRecordUpsertData,
    DecisionRecordUpsertData,
    EvalResultCreateData,
    ExtractedItemRecordUpsertData,
    SqlAlchemyMonitorRunRepository,
    build_monitor_run_repository,
    build_topic_repository,
)
from app.storage.redis_store import build_redis_client

def test_settings_accept_explicit_connection_values() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
    )

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.redis_url.startswith("redis://")
    assert settings.default_push_threshold == 0.72


def test_settings_accept_eval_judge_provider_values() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        judge_provider="openai_compatible",
        judge_base_url="https://judge.example.com/v1",
        judge_api_key="test-key",
        judge_model="judge-model",
        judge_timeout_seconds=3.5,
    )

    assert settings.judge_provider == "openai_compatible"
    assert settings.judge_base_url == "https://judge.example.com/v1"
    assert settings.judge_api_key == "test-key"
    assert settings.judge_model == "judge-model"
    assert settings.judge_timeout_seconds == 3.5


def test_settings_accept_browser_fetch_provider_values() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        browser_fetch_provider="playwright_mcp",
        playwright_mcp_base_url="http://localhost:8931",
        playwright_mcp_timeout_seconds=4.0,
        browser_allowed_domains=["example.com", "news.example.com"],
        browser_max_concurrency=1,
        browser_max_content_chars=2048,
    )

    assert settings.browser_fetch_provider == "playwright_mcp"
    assert settings.playwright_mcp_base_url == "http://localhost:8931"
    assert settings.playwright_mcp_timeout_seconds == 4.0
    assert settings.browser_allowed_domains == ["example.com", "news.example.com"]
    assert settings.browser_max_concurrency == 1
    assert settings.browser_max_content_chars == 2048


def test_settings_accept_history_index_provider_values() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        history_index_provider="opensearch",
        opensearch_base_url="http://localhost:9200",
        opensearch_index_name="industry-news-candidates",
        opensearch_timeout_seconds=4.0,
    )

    assert settings.history_index_provider == "opensearch"
    assert settings.opensearch_base_url == "http://localhost:9200"
    assert settings.opensearch_index_name == "industry-news-candidates"
    assert settings.opensearch_timeout_seconds == 4.0


def test_settings_accept_semantic_dedup_values() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        semantic_dedup_provider="local",
        semantic_dedup_threshold=0.82,
    )

    assert settings.semantic_dedup_provider == "local"
    assert settings.semantic_dedup_threshold == 0.82


def test_settings_accept_notification_webhook_values() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        notification_provider="webhook",
        notification_webhook_url="https://hooks.example.com/news",
        notification_timeout_seconds=3.5,
    )

    assert settings.notification_provider == "webhook"
    assert settings.notification_webhook_url == "https://hooks.example.com/news"
    assert settings.notification_timeout_seconds == 3.5


def test_settings_accept_onesearch_gateway_provider_values() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        mcp_gateway_provider="onesearch",
        onesearch_base_url="http://localhost:8090",
        onesearch_timeout_seconds=4.5,
        onesearch_max_results=7,
    )

    assert settings.mcp_gateway_provider == "onesearch"
    assert settings.onesearch_base_url == "http://localhost:8090"
    assert settings.onesearch_timeout_seconds == 4.5
    assert settings.onesearch_max_results == 7


def test_settings_reject_invalid_onesearch_gateway_provider_value() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
            redis_url="redis://localhost:6379/0",
            mcp_gateway_provider="one_search",
        )


def test_notification_tool_skips_when_provider_disabled() -> None:
    from app.tools.notification_tool import NotificationSendTool

    response = NotificationSendTool(provider="none")(
        run_id="run_001",
        topic_id="topic_001",
        push_records=[{"push_id": "push_001"}],
    )

    assert response.success is True
    assert response.data is not None
    assert response.data["status"] == "skipped"
    assert response.metadata["notification_provider"] == "none"


def test_notification_tool_posts_push_records_to_webhook() -> None:
    from app.tools.notification_tool import NotificationSendTool

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeHttpClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def post(
            self,
            url: str,
            json: dict[str, object],
            timeout: float,
        ) -> FakeResponse:
            self.requests.append({"url": url, "json": json, "timeout": timeout})
            return FakeResponse()

    http_client = FakeHttpClient()
    response = NotificationSendTool(
        provider="webhook",
        webhook_url="https://hooks.example.com/news",
        http_client=http_client,
        timeout_seconds=4.0,
    )(
        run_id="run_001",
        topic_id="topic_001",
        push_records=[
            {
                "push_id": "push_001",
                "title": "OpenAI ships agent workflow",
                "url": "https://example.com/agent",
                "summary": "Enterprise agent workflow.",
                "score": 0.91,
                "decision_reason": "score meets threshold",
                "ignored_extra": "not sent",
            }
        ],
    )

    assert response.success is True
    assert response.data is not None
    assert response.data["status"] == "sent"
    assert response.data["sent_count"] == 1
    assert response.metadata["notification_provider"] == "webhook"
    assert http_client.requests[0]["url"] == "https://hooks.example.com/news"
    assert http_client.requests[0]["timeout"] == 4.0
    payload = http_client.requests[0]["json"]
    assert payload["run_id"] == "run_001"
    assert payload["topic_id"] == "topic_001"
    assert payload["push_count"] == 1
    assert payload["push_records"] == [
        {
            "push_id": "push_001",
            "title": "OpenAI ships agent workflow",
            "url": "https://example.com/agent",
            "summary": "Enterprise agent workflow.",
            "score": 0.91,
            "decision_reason": "score meets threshold",
        }
    ]


def test_notification_tool_fails_when_webhook_url_missing() -> None:
    from app.tools.notification_tool import NotificationSendTool

    response = NotificationSendTool(provider="webhook")(
        run_id="run_001",
        topic_id="topic_001",
        push_records=[{"push_id": "push_001"}],
    )

    assert response.success is False
    assert response.error is not None
    assert response.error.code == "notification_webhook_not_configured"
    assert response.metadata["notification_provider"] == "webhook"


def test_notification_tool_normalizes_webhook_http_failure() -> None:
    from app.tools.notification_tool import NotificationSendTool

    class FakeHttpClient:
        def post(
            self,
            url: str,
            json: dict[str, object],
            timeout: float,
        ) -> object:
            raise RuntimeError("webhook unavailable")

    response = NotificationSendTool(
        provider="webhook",
        webhook_url="https://hooks.example.com/news",
        http_client=FakeHttpClient(),
    )(
        run_id="run_001",
        topic_id="topic_001",
        push_records=[{"push_id": "push_001"}],
    )

    assert response.success is False
    assert response.error is not None
    assert response.error.code == "notification_webhook_failed"
    assert response.error.message == "webhook unavailable"
    assert response.metadata["notification_provider"] == "webhook"


def test_build_default_tool_registry_wires_webhook_notification() -> None:
    from app.tools.registry import build_default_tool_registry

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeHttpClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def post(
            self,
            url: str,
            json: dict[str, object],
            timeout: float,
        ) -> FakeResponse:
            self.requests.append({"url": url, "json": json, "timeout": timeout})
            return FakeResponse()

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        notification_provider="webhook",
        notification_webhook_url="https://hooks.example.com/news",
        notification_timeout_seconds=2.5,
    )
    http_client = FakeHttpClient()
    registry = build_default_tool_registry(
        llm=MockLLM(),
        settings=settings,
        notification_http_client=http_client,
    )
    gateway = LocalToolGateway()
    registry.register_into(gateway)

    response = gateway.call(
        "notification_send",
        run_id="run_001",
        topic_id="topic_001",
        push_records=[{"push_id": "push_001"}],
    )

    assert response.success is True
    assert response.data["status"] == "sent"
    assert http_client.requests[0]["url"] == "https://hooks.example.com/news"
    assert http_client.requests[0]["timeout"] == 2.5


@pytest.mark.parametrize("threshold", [0.0, -0.1, 1.1])
def test_settings_reject_invalid_semantic_dedup_threshold(
    threshold: float,
) -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
            redis_url="redis://localhost:6379/0",
            semantic_dedup_provider="local",
            semantic_dedup_threshold=threshold,
        )


def test_settings_read_connection_values_from_environment(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://env_user:env_pass@localhost:5432/env_agent",
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/9")

    settings = Settings()

    assert settings.database_url == (
        "postgresql+psycopg://env_user:env_pass@localhost:5432/env_agent"
    )
    assert settings.redis_url == "redis://localhost:6379/9"


def test_get_settings_does_not_keep_stale_environment_values(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://first:first@localhost:5432/first_agent",
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/1")

    first_settings = get_settings()

    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://second:second@localhost:5432/second_agent",
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/2")

    second_settings = get_settings()

    assert first_settings.database_url != second_settings.database_url
    assert second_settings.database_url == (
        "postgresql+psycopg://second:second@localhost:5432/second_agent"
    )
    assert second_settings.redis_url == "redis://localhost:6379/2"


def test_settings_env_file_path_is_stable() -> None:
    expected_env_file = Path(__file__).resolve().parents[1] / ".env"
    configured_env_file = Path(Settings.model_config["env_file"])

    assert configured_env_file.is_absolute()
    assert configured_env_file.resolve() == expected_env_file


def test_topic_model_declares_mvp_table_and_required_columns() -> None:
    assert Topic.__tablename__ == "topics"
    required_columns = {
        "topic_id",
        "name",
        "description",
        "seed_keywords",
        "trusted_sources",
        "exclude_keywords",
        "push_threshold",
        "cooldown_hours",
        "enabled",
        "schedule_cron",
        "created_at",
        "updated_at",
    }

    assert required_columns.issubset(Topic.__table__.columns.keys())


def test_candidate_model_declares_phase2_memory_columns() -> None:
    assert CandidateRecord.__tablename__ == "candidates"
    required_columns = {
        "candidate_id",
        "run_id",
        "topic_id",
        "source_type",
        "source_name",
        "title",
        "url",
        "published_at",
        "raw_summary",
        "fetch_status",
        "content",
        "structured_payload",
        "score",
        "decision",
        "decision_reason",
        "created_at",
    }

    assert required_columns.issubset(CandidateRecord.__table__.columns.keys())


def test_extracted_item_model_declares_phase2_memory_columns() -> None:
    assert ExtractedItemRecord.__tablename__ == "extracted_items"
    required_columns = {
        "extracted_id",
        "run_id",
        "topic_id",
        "candidate_id",
        "source_type",
        "source_name",
        "title",
        "url",
        "published_at",
        "summary",
        "keywords",
        "content",
        "content_fingerprint",
        "fetch_status",
        "fetch_error",
        "extraction_mode",
        "structured_payload",
        "created_at",
    }

    assert required_columns.issubset(ExtractedItemRecord.__table__.columns.keys())


def test_decision_record_model_declares_phase2_memory_columns() -> None:
    assert DecisionRecord.__tablename__ == "decision_records"
    required_columns = {
        "decision_id",
        "run_id",
        "topic_id",
        "candidate_id",
        "extracted_id",
        "source_type",
        "source_name",
        "title",
        "url",
        "published_at",
        "summary",
        "score",
        "should_push",
        "decision_reason",
        "decision_payload",
        "created_at",
    }

    assert required_columns.issubset(DecisionRecord.__table__.columns.keys())


def test_eval_result_model_declares_phase2_memory_columns() -> None:
    assert EvalResult.__tablename__ == "eval_results"
    required_columns = {
        "eval_id",
        "run_id",
        "topic_id",
        "retrieved_count",
        "deduped_count",
        "dedup_rate",
        "push_count",
        "duplicate_push_count",
        "tool_success_rate",
        "fetch_success_rate",
        "trace_completeness",
        "raw_summary_count",
        "browser_fallback_count",
        "provider_fallback_count",
        "judge_mode",
        "judge_score",
        "judge_reason",
        "judge_issues",
        "suggestions",
        "created_at",
    }

    assert required_columns.issubset(EvalResult.__table__.columns.keys())


def test_mock_eval_judge_scores_quality_metrics() -> None:
    result = MockEvalJudge().judge(
        {
            "duplicate_push_count": 1,
            "fetch_success_rate": 0.5,
            "trace_completeness": 0.75,
        }
    )

    assert result["judge_mode"] == "mock_rule_judge"
    assert result["judge_score"] == 0.6
    assert "duplicate push" in result["judge_reason"]
    assert result["judge_issues"] == [
        "duplicate_push_detected",
        "fetch_degraded",
        "trace_incomplete",
    ]


def test_openai_compatible_eval_judge_parses_json_response() -> None:
    class FakeJudgeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"judge_score": 0.82, "judge_reason": "Useful.", '
                                '"judge_issues": ["trace_incomplete"]}'
                            )
                        }
                    }
                ]
            }

    class FakeJudgeClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def post(self, url: str, **kwargs: object) -> FakeJudgeResponse:
            self.requests.append({"url": url, **kwargs})
            return FakeJudgeResponse()

    client = FakeJudgeClient()
    judge = OpenAICompatibleEvalJudge(
        base_url="https://judge.example.com/v1",
        api_key="test-key",
        model="judge-model",
        http_client=client,
    )

    result = judge.judge({"push_count": 1, "trace_completeness": 0.75})

    assert result == {
        "judge_mode": "openai_compatible_judge",
        "judge_score": 0.82,
        "judge_reason": "Useful.",
        "judge_issues": ["trace_incomplete"],
    }
    assert client.requests[0]["url"] == "https://judge.example.com/v1/chat/completions"
    assert client.requests[0]["headers"] == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
    }


def test_eval_judge_builder_falls_back_to_mock_when_provider_fails() -> None:
    class FailingJudgeClient:
        def post(self, url: str, **kwargs: object) -> object:
            raise RuntimeError("judge unavailable")

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        judge_provider="openai_compatible",
        judge_base_url="https://judge.example.com/v1",
        judge_api_key="test-key",
    )
    judge = build_eval_judge(settings=settings, http_client=FailingJudgeClient())

    result = judge.judge(
        {
            "duplicate_push_count": 0,
            "fetch_success_rate": 1.0,
            "trace_completeness": 1.0,
        }
    )

    assert result["judge_mode"] == "mock_rule_judge"
    assert result["judge_score"] == 1.0
    assert "judge_provider_fallback" in result["judge_issues"]
    assert "judge unavailable" in result["judge_reason"]


def test_sqlalchemy_repository_upserts_and_lists_candidate_records() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
    )
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as session:
        repository = SqlAlchemyMonitorRunRepository(session=session)

        created = repository.upsert_candidate_records(
            (
                CandidateRecordUpsertData(
                    candidate_id="cand_001",
                    run_id="run_001",
                    topic_id="topic_ai_agent",
                    source_type="search",
                    source_name="Mock Search",
                    title="Initial candidate",
                    url="https://example.com/initial",
                    published_at=datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
                    raw_summary="Initial summary",
                    fetch_status="pending",
                    content=None,
                    structured_payload={"decision": {}},
                    score=None,
                    decision=None,
                    decision_reason=None,
                ),
            )
        )
        updated = repository.upsert_candidate_records(
            (
                CandidateRecordUpsertData(
                    candidate_id="cand_001",
                    run_id="run_001",
                    topic_id="topic_ai_agent",
                    source_type="search",
                    source_name="Mock Search",
                    title="Updated candidate",
                    url="https://example.com/updated",
                    published_at=None,
                    raw_summary="Updated summary",
                    fetch_status="success",
                    content="Fetched article body",
                    structured_payload={"decision": {"should_push": True}},
                    score=0.91,
                    decision="push",
                    decision_reason="Above threshold",
                ),
            )
        )
        listed = repository.list_candidate_records("run_001")

    assert created[0]["title"] == "Initial candidate"
    assert updated[0]["title"] == "Updated candidate"
    assert [candidate["candidate_id"] for candidate in listed] == ["cand_001"]
    assert listed[0]["fetch_status"] == "success"
    assert listed[0]["score"] == 0.91
    assert listed[0]["structured_payload"]["decision"]["should_push"] is True


def test_sqlalchemy_repository_upserts_and_lists_extracted_item_records() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
    )
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as session:
        repository = SqlAlchemyMonitorRunRepository(session=session)

        created = repository.upsert_extracted_item_records(
            (
                ExtractedItemRecordUpsertData(
                    extracted_id="ext_cand_001",
                    run_id="run_001",
                    topic_id="topic_ai_agent",
                    candidate_id="cand_001",
                    source_type="search",
                    source_name="Mock Search",
                    title="Initial extracted title",
                    url="https://example.com/initial",
                    published_at=datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
                    summary="Initial summary",
                    keywords=("agent", "automation"),
                    content="Fetched body",
                    content_fingerprint="fp_initial",
                    fetch_status="fetched",
                    fetch_error=None,
                    extraction_mode="full_content",
                    structured_payload={"quality": {"source": "mock"}},
                ),
            )
        )
        updated = repository.upsert_extracted_item_records(
            (
                ExtractedItemRecordUpsertData(
                    extracted_id="ext_cand_001",
                    run_id="run_001",
                    topic_id="topic_ai_agent",
                    candidate_id="cand_001",
                    source_type="search",
                    source_name="Mock Search",
                    title="Updated extracted title",
                    url="https://example.com/updated",
                    published_at=None,
                    summary="Updated summary",
                    keywords=("agent", "launch"),
                    content="Updated body",
                    content_fingerprint="fp_updated",
                    fetch_status="fetched",
                    fetch_error=None,
                    extraction_mode="full_content",
                    structured_payload={"quality": {"source": "updated"}},
                ),
            )
        )
        listed = repository.list_extracted_item_records("run_001")

    assert created[0]["title"] == "Initial extracted title"
    assert updated[0]["title"] == "Updated extracted title"
    assert [item["extracted_id"] for item in listed] == ["ext_cand_001"]
    assert listed[0]["keywords"] == ["agent", "launch"]
    assert listed[0]["content_fingerprint"] == "fp_updated"
    assert listed[0]["structured_payload"]["quality"]["source"] == "updated"


def test_sqlalchemy_repository_upserts_and_lists_decision_records() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
    )
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as session:
        repository = SqlAlchemyMonitorRunRepository(session=session)

        created = repository.upsert_decision_records(
            (
                DecisionRecordUpsertData(
                    decision_id="dec_001",
                    run_id="run_001",
                    topic_id="topic_ai_agent",
                    candidate_id="cand_001",
                    extracted_id="ext_001",
                    source_type="search",
                    source_name="Mock Search",
                    title="Initial decision",
                    url="https://example.com/initial",
                    published_at=datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
                    summary="Initial summary",
                    score=0.61,
                    should_push=False,
                    decision_reason="Below threshold",
                    decision_payload={"should_push": False},
                ),
            )
        )
        updated = repository.upsert_decision_records(
            (
                DecisionRecordUpsertData(
                    decision_id="dec_001",
                    run_id="run_001",
                    topic_id="topic_ai_agent",
                    candidate_id="cand_001",
                    extracted_id="ext_001",
                    source_type="search",
                    source_name="Mock Search",
                    title="Updated decision",
                    url="https://example.com/updated",
                    published_at=None,
                    summary="Updated summary",
                    score=0.93,
                    should_push=True,
                    decision_reason="Above threshold",
                    decision_payload={"should_push": True},
                ),
            )
        )
        listed = repository.list_decision_records("run_001")

    assert created[0]["title"] == "Initial decision"
    assert updated[0]["title"] == "Updated decision"
    assert [decision["decision_id"] for decision in listed] == ["dec_001"]
    assert listed[0]["should_push"] is True
    assert listed[0]["decision_payload"]["should_push"] is True


def test_sqlalchemy_repository_persists_richer_eval_metrics() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
    )
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as session:
        repository = SqlAlchemyMonitorRunRepository(session=session)
        persisted = repository.create_eval_result(
            EvalResultCreateData(
                run_id="run_001",
                topic_id="topic_ai_agent",
                retrieved_count=9,
                deduped_count=6,
                dedup_rate=0.33,
                push_count=2,
                duplicate_push_count=1,
                tool_success_rate=0.8,
                fetch_success_rate=0.67,
                trace_completeness=0.92,
                raw_summary_count=4,
                browser_fallback_count=2,
                provider_fallback_count=1,
                judge_mode="mock_rule_judge",
                judge_score=0.85,
                judge_reason="Quality is acceptable.",
                judge_issues=("fetch_degraded",),
                suggestions=("one", "two"),
            )
        )
        loaded = repository.get_eval_result("run_001")

    assert persisted["raw_summary_count"] == 4
    assert persisted["browser_fallback_count"] == 2
    assert persisted["provider_fallback_count"] == 1
    assert loaded is not None
    assert loaded["raw_summary_count"] == 4
    assert loaded["browser_fallback_count"] == 2
    assert loaded["provider_fallback_count"] == 1
    assert loaded["judge_mode"] == "mock_rule_judge"
    assert loaded["judge_score"] == 0.85
    assert loaded["judge_reason"] == "Quality is acceptable."
    assert loaded["judge_issues"] == ["fetch_degraded"]


def test_sqlalchemy_repository_persists_eval_judge_fields() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
    )
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as session:
        repository = SqlAlchemyMonitorRunRepository(session=session)
        persisted = repository.create_eval_result(
            EvalResultCreateData(
                run_id="run_judged",
                topic_id="topic_ai_agent",
                retrieved_count=3,
                deduped_count=2,
                dedup_rate=0.33,
                push_count=1,
                duplicate_push_count=1,
                tool_success_rate=1.0,
                fetch_success_rate=0.5,
                trace_completeness=0.75,
                raw_summary_count=1,
                browser_fallback_count=0,
                provider_fallback_count=0,
                judge_mode="mock_rule_judge",
                judge_score=0.6,
                judge_reason="Mock judge detected degraded quality.",
                judge_issues=("duplicate_push_detected", "fetch_degraded"),
                suggestions=(),
            )
        )
        loaded = repository.get_eval_result("run_judged")

    assert persisted["judge_mode"] == "mock_rule_judge"
    assert persisted["judge_score"] == 0.6
    assert persisted["judge_reason"] == "Mock judge detected degraded quality."
    assert persisted["judge_issues"] == ["duplicate_push_detected", "fetch_degraded"]
    assert loaded is not None
    assert loaded["judge_issues"] == ["duplicate_push_detected", "fetch_degraded"]


def test_sqlalchemy_repository_summarizes_eval_quality_metrics() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
    )
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as session:
        repository = SqlAlchemyMonitorRunRepository(session=session)
        repository.create_eval_result(
            EvalResultCreateData(
                run_id="run_001",
                topic_id="topic_ai_agent",
                retrieved_count=6,
                deduped_count=4,
                dedup_rate=0.33,
                push_count=1,
                duplicate_push_count=0,
                tool_success_rate=1.0,
                fetch_success_rate=0.5,
                trace_completeness=0.9,
                raw_summary_count=2,
                browser_fallback_count=1,
                provider_fallback_count=1,
                suggestions=(),
            )
        )
        repository.create_eval_result(
            EvalResultCreateData(
                run_id="run_002",
                topic_id="topic_ai_agent",
                retrieved_count=8,
                deduped_count=7,
                dedup_rate=0.12,
                push_count=3,
                duplicate_push_count=1,
                tool_success_rate=0.5,
                fetch_success_rate=1.0,
                trace_completeness=1.0,
                raw_summary_count=0,
                browser_fallback_count=2,
                provider_fallback_count=0,
                suggestions=("review provider fallback",),
            )
        )
        summary = repository.get_eval_summary()

    assert summary is not None
    assert summary["run_count"] == 2
    assert summary["total_push_count"] == 4
    assert summary["total_duplicate_push_count"] == 1
    assert summary["total_raw_summary_count"] == 2
    assert summary["total_browser_fallback_count"] == 3
    assert summary["total_provider_fallback_count"] == 1
    assert summary["avg_tool_success_rate"] == 0.75
    assert summary["avg_fetch_success_rate"] == 0.75
    assert summary["avg_trace_completeness"] == 0.95
    assert summary["latest_eval"]["run_id"] == "run_002"


def test_sqlalchemy_repository_round_trips_all_phase_a_entities(
    seeded_phase_a_sqlalchemy,
) -> None:
    with seeded_phase_a_sqlalchemy.session_factory() as session:
        topic_repository = build_topic_repository(session)
        run_repository = build_monitor_run_repository(session)

        loaded_topic = topic_repository.get_topic(seeded_phase_a_sqlalchemy.topic_id)
        loaded_run = run_repository.get_monitor_run(seeded_phase_a_sqlalchemy.run_id)
        candidate_records = run_repository.list_candidate_records(
            seeded_phase_a_sqlalchemy.run_id
        )
        extracted_records = run_repository.list_extracted_item_records(
            seeded_phase_a_sqlalchemy.run_id
        )
        decision_records = run_repository.list_decision_records(
            seeded_phase_a_sqlalchemy.run_id
        )
        push_records = run_repository.list_push_records(
            run_id=seeded_phase_a_sqlalchemy.run_id
        )
        run_events = run_repository.list_run_events(seeded_phase_a_sqlalchemy.run_id)
        eval_result = run_repository.get_eval_result(seeded_phase_a_sqlalchemy.run_id)

    assert loaded_topic is not None
    assert loaded_topic.name == "AI Agent"
    assert loaded_run is not None
    assert loaded_run.status == "completed"
    assert loaded_run.state_snapshot["trigger"] == "scheduler"
    assert [candidate["candidate_id"] for candidate in candidate_records] == ["cand_001"]
    assert [item["extracted_id"] for item in extracted_records] == ["ext_001"]
    assert [decision["decision_id"] for decision in decision_records] == ["dec_001"]
    assert [push["candidate_id"] for push in push_records] == ["cand_001"]
    assert [event["event_type"] for event in run_events] == ["notification_sent"]
    assert eval_result is not None
    assert eval_result["run_id"] == seeded_phase_a_sqlalchemy.run_id
    assert eval_result["push_count"] == 1


def test_monitor_detail_endpoints_read_persisted_phase_a_entities(
    seeded_phase_a_sqlalchemy,
    sqlalchemy_client_factory,
) -> None:
    with sqlalchemy_client_factory(seeded_phase_a_sqlalchemy.session_factory) as client:
        run_response = client.get(
            f"/api/monitor/runs/{seeded_phase_a_sqlalchemy.run_id}"
        )
        candidates_response = client.get(
            f"/api/monitor/runs/{seeded_phase_a_sqlalchemy.run_id}/candidates"
        )
        events_response = client.get(
            f"/api/monitor/runs/{seeded_phase_a_sqlalchemy.run_id}/events"
        )
        pushes_response = client.get("/api/pushes")
        latest_eval_response = client.post("/api/eval/run")
        summary_response = client.get("/api/eval/summary")

    assert run_response.status_code == 200
    assert run_response.json()["run_id"] == seeded_phase_a_sqlalchemy.run_id
    assert run_response.json()["status"] == "completed"
    assert run_response.json()["candidate_items"] == [
        {
            "candidate_id": "cand_001",
            "title": "OpenAI agent update",
            "url": "https://example.com/agent-update",
        }
    ]
    assert run_response.json()["final_decisions"] == [
        {
            "candidate_id": "cand_001",
            "should_push": True,
            "decision_reason": "Above threshold",
        }
    ]

    assert candidates_response.status_code == 200
    assert candidates_response.json()["run_id"] == seeded_phase_a_sqlalchemy.run_id
    assert [candidate["candidate_id"] for candidate in candidates_response.json()["candidates"]] == [
        "cand_001"
    ]

    assert events_response.status_code == 200
    assert events_response.json()["run_id"] == seeded_phase_a_sqlalchemy.run_id
    assert [event["event_type"] for event in events_response.json()["events"]] == [
        "notification_sent"
    ]

    assert pushes_response.status_code == 200
    assert [push["candidate_id"] for push in pushes_response.json()["pushes"]] == ["cand_001"]

    assert latest_eval_response.status_code == 200
    assert latest_eval_response.json()["run_id"] == seeded_phase_a_sqlalchemy.run_id
    assert latest_eval_response.json()["push_count"] == 1

    assert summary_response.status_code == 200
    assert summary_response.json()["run_count"] == 1
    assert summary_response.json()["latest_eval"]["run_id"] == seeded_phase_a_sqlalchemy.run_id
    assert summary_response.json()["latest_eval"]["push_count"] == 1


def test_score_run_reports_phase2_quality_fallback_metrics() -> None:
    result = score_run(
        {
            "candidate_items": [{}, {}, {}],
            "deduped_items": [{}, {}],
            "push_records": [{}],
            "final_decisions": [
                {"decision_reason": "canonical_url already exists in push_history"},
                {"decision_reason": "score 0.91 meets threshold"},
            ],
            "fetched_contents": [
                {"fetch_status": "fetched", "fetch_method": "http"},
                {"fetch_status": "fetched", "fetch_method": "browser_fallback"},
                {"fetch_status": "failed"},
            ],
            "extracted_items": [
                {"extraction_mode": "raw_summary"},
                {"extraction_mode": "full_content"},
            ],
            "tool_results": [
                {
                    "success": True,
                    "metadata": {
                        "used_fallback": True,
                        "fallback_provider": "mock_search",
                    },
                },
                {
                    "success": True,
                    "metadata": {"used_browser_fallback": True},
                },
            ],
            "events": [{"node": node} for node in score_run.__globals__["REQUIRED_TRACE_NODES"]],
        }
    )

    assert result["raw_summary_count"] == 1
    assert result["browser_fallback_count"] == 2
    assert result["provider_fallback_count"] == 1


def test_build_session_factory_binds_to_provided_engine() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
    )

    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    assert session_factory.kw["bind"] is engine


def test_get_session_factory_reuses_registry_engine_for_same_database_url() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/reuse_agent",
        redis_url="redis://localhost:6379/0",
    )
    reset_engine_registry()

    first_factory = get_session_factory(settings)
    second_factory = get_session_factory(settings)

    assert first_factory.kw["bind"] is second_factory.kw["bind"]
    assert first_factory.kw["bind"] is get_engine(settings)


def test_reset_engine_registry_disposes_and_rebuilds_engine() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/reset_agent",
        redis_url="redis://localhost:6379/0",
    )
    reset_engine_registry()

    first_engine = get_engine(settings)

    reset_engine_registry(settings.database_url)

    second_engine = get_engine(settings)

    assert first_engine is not second_engine


def test_build_redis_client_uses_runtime_settings_url() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/5",
    )

    client = build_redis_client(settings)

    assert client.connection_pool.connection_kwargs["decode_responses"] is True
    assert client.connection_pool.connection_kwargs["db"] == 5


def test_build_run_queue_falls_back_to_memory_when_redis_ping_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingRedis:
        def ping(self) -> bool:
            raise RedisError("redis unavailable")

    monkeypatch.setattr(
        "app.scheduler.worker.build_redis_client",
        lambda settings=None: FailingRedis(),
    )

    queue = build_run_queue(
        Settings(
            database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
            redis_url="redis://localhost:6379/0",
        )
    )

    assert isinstance(queue, InMemoryRunQueue)


def test_redis_stream_run_queue_acknowledges_only_after_explicit_success() -> None:
    class FakeRedisStreamClient:
        def __init__(self) -> None:
            self.created_groups: list[dict[str, object]] = []
            self.added: list[dict[str, object]] = []
            self.acked: list[dict[str, object]] = []

        def xgroup_create(
            self,
            name: str,
            groupname: str,
            id: str,
            mkstream: bool,
        ) -> None:
            self.created_groups.append(
                {
                    "name": name,
                    "groupname": groupname,
                    "id": id,
                    "mkstream": mkstream,
                }
            )

        def xadd(self, name: str, fields: dict[str, str]) -> str:
            self.added.append({"name": name, "fields": fields})
            return "1710000000000-0"

        def xreadgroup(
            self,
            groupname: str,
            consumername: str,
            streams: dict[str, str],
            count: int,
            block: int,
        ) -> list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]:
            assert groupname == "monitor-workers"
            assert consumername == "worker-1"
            assert streams == {"industry_news_agent:run_stream": ">"}
            assert count == 1
            assert block == 0
            return [
                (
                    b"industry_news_agent:run_stream",
                    [
                        (
                            b"1710000000000-0",
                            {
                                b"topic_id": b"topic_ai_agent",
                                b"trigger": b"scheduler",
                                b"enqueued_at": b"2026-06-09T12:00:00Z",
                            },
                        )
                    ],
                )
            ]

        def xack(self, name: str, groupname: str, id: bytes) -> int:
            self.acked.append({"name": name, "groupname": groupname, "id": id})
            return 1

    client = FakeRedisStreamClient()
    queue = RedisStreamRunQueue(
        client,
        stream_key="industry_news_agent:run_stream",
        group_name="monitor-workers",
        consumer_name="worker-1",
    )

    enqueue_result = queue.enqueue(
        RunQueueMessage(
            topic_id="topic_ai_agent",
            trigger="scheduler",
            enqueued_at=datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
        )
    )
    message = queue.dequeue()

    assert enqueue_result["status"] == "queued"
    assert enqueue_result["message_id"] == "1710000000000-0"
    assert message is not None
    assert message.topic_id == "topic_ai_agent"
    assert message.trigger == "scheduler"
    assert message.enqueued_at == datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
    assert message.queue_message_id == "1710000000000-0"
    assert message.queue_stream == "industry_news_agent:run_stream"
    assert client.created_groups == [
        {
            "name": "industry_news_agent:run_stream",
            "groupname": "monitor-workers",
            "id": "0",
            "mkstream": True,
        }
    ]
    assert client.added == [
        {
            "name": "industry_news_agent:run_stream",
            "fields": {
                "topic_id": "topic_ai_agent",
                "trigger": "scheduler",
                "enqueued_at": "2026-06-09T12:00:00Z",
            },
        }
    ]
    assert client.acked == []

    queue.acknowledge(message)

    assert client.acked == [
        {
            "name": "industry_news_agent:run_stream",
            "groupname": "monitor-workers",
            "id": b"1710000000000-0",
        }
    ]


def test_redis_stream_run_queue_requeues_failed_delivery() -> None:
    class FakeRedisStreamClient:
        def __init__(self) -> None:
            self.created_groups: list[dict[str, object]] = []
            self.added: list[dict[str, object]] = []
            self.acked: list[dict[str, object]] = []

        def xgroup_create(
            self,
            name: str,
            groupname: str,
            id: str,
            mkstream: bool,
        ) -> None:
            self.created_groups.append(
                {
                    "name": name,
                    "groupname": groupname,
                    "id": id,
                    "mkstream": mkstream,
                }
            )

        def xadd(self, name: str, fields: dict[str, str]) -> str:
            self.added.append({"name": name, "fields": fields})
            return "1710000000001-0"

        def xreadgroup(
            self,
            groupname: str,
            consumername: str,
            streams: dict[str, str],
            count: int,
            block: int,
        ) -> list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]:
            return [
                (
                    b"industry_news_agent:run_stream",
                    [
                        (
                            b"1710000000000-0",
                            {
                                b"topic_id": b"topic_ai_agent",
                                b"trigger": b"scheduler",
                                b"enqueued_at": b"2026-06-09T12:00:00Z",
                            },
                        )
                    ],
                )
            ]

        def xack(self, name: str, groupname: str, id: bytes) -> int:
            self.acked.append({"name": name, "groupname": groupname, "id": id})
            return 1

    client = FakeRedisStreamClient()
    queue = RedisStreamRunQueue(client)

    message = queue.dequeue()

    assert message is not None
    message = RunQueueMessage(
        topic_id=message.topic_id,
        trigger=message.trigger,
        enqueued_at=message.enqueued_at,
        queue_message_id=message.queue_message_id,
        queue_stream=message.queue_stream,
        retry_count=message.retry_count,
        max_retries=2,
    )
    assert client.added == []
    assert client.acked == []

    queue.requeue(message, reason="transient failure")

    assert len(client.added) == 1
    requeued_payload = client.added[0]
    assert requeued_payload["name"] == "industry_news_agent:run_stream"
    assert requeued_payload["fields"]["topic_id"] == "topic_ai_agent"
    assert requeued_payload["fields"]["trigger"] == "scheduler"
    assert requeued_payload["fields"]["retry_reason"] == "transient failure"
    assert requeued_payload["fields"]["retry_count"] == "1"
    assert requeued_payload["fields"]["max_retries"] == "2"
    assert requeued_payload["fields"]["enqueued_at"] != "2026-06-09T12:00:00Z"
    assert datetime.fromisoformat(
        str(requeued_payload["fields"]["enqueued_at"]).replace("Z", "+00:00")
    ) > datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
    assert client.acked == [
        {
            "name": "industry_news_agent:run_stream",
            "groupname": "monitor-workers",
            "id": b"1710000000000-0",
        }
    ]


def test_redis_stream_run_queue_round_trip_preserves_retry_metadata() -> None:
    class FakeRedisStreamClient:
        def __init__(self) -> None:
            self.created_groups: list[dict[str, object]] = []
            self.added: list[dict[str, object]] = []

        def xgroup_create(
            self,
            name: str,
            groupname: str,
            id: str,
            mkstream: bool,
        ) -> None:
            self.created_groups.append(
                {
                    "name": name,
                    "groupname": groupname,
                    "id": id,
                    "mkstream": mkstream,
                }
            )

        def xadd(self, name: str, fields: dict[str, str]) -> str:
            self.added.append({"name": name, "fields": fields})
            return "1710000000001-0"

        def xreadgroup(
            self,
            groupname: str,
            consumername: str,
            streams: dict[str, str],
            count: int,
            block: int,
        ) -> list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]:
            return [
                (
                    b"industry_news_agent:run_stream",
                    [
                        (
                            b"1710000000001-0",
                            {
                                b"topic_id": b"topic_ai_agent",
                                b"trigger": b"scheduler",
                                b"enqueued_at": b"2026-06-09T12:05:00Z",
                                b"retry_reason": b"worker_retry",
                                b"retry_count": b"1",
                                b"max_retries": b"2",
                            },
                        )
                    ],
                )
            ]

    client = FakeRedisStreamClient()
    queue = RedisStreamRunQueue(client)

    message = queue.dequeue()

    assert message is not None
    assert message.retry_reason == "worker_retry"
    assert message.retry_count == 1
    assert message.max_retries == 2


def test_redis_stream_run_queue_round_trip_preserves_run_id() -> None:
    class FakeRedisStreamClient:
        def __init__(self) -> None:
            self.created_groups: list[dict[str, object]] = []
            self.added: list[dict[str, object]] = []

        def xgroup_create(
            self,
            name: str,
            groupname: str,
            id: str,
            mkstream: bool,
        ) -> None:
            self.created_groups.append(
                {
                    "name": name,
                    "groupname": groupname,
                    "id": id,
                    "mkstream": mkstream,
                }
            )

        def xadd(self, name: str, fields: dict[str, str]) -> str:
            self.added.append({"name": name, "fields": fields})
            return "1710000000001-0"

        def xreadgroup(
            self,
            groupname: str,
            consumername: str,
            streams: dict[str, str],
            count: int,
            block: int,
        ) -> list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]:
            return [
                (
                    b"industry_news_agent:run_stream",
                    [
                        (
                            b"1710000000001-0",
                            {
                                b"topic_id": b"topic_ai_agent",
                                b"trigger": b"scheduler",
                                b"run_id": b"run_retry_001",
                                b"enqueued_at": b"2026-06-09T12:05:00Z",
                                b"retry_reason": b"worker_retry",
                                b"retry_count": b"1",
                                b"max_retries": b"2",
                            },
                        )
                    ],
                )
            ]

    client = FakeRedisStreamClient()
    queue = RedisStreamRunQueue(client)

    queue.enqueue(
        RunQueueMessage(
            topic_id="topic_ai_agent",
            trigger="scheduler",
            run_id="run_retry_001",
            enqueued_at=datetime(2026, 6, 9, 12, 5, tzinfo=UTC),
            retry_reason="worker_retry",
            retry_count=1,
            max_retries=2,
        )
    )
    message = queue.dequeue()

    assert client.added[0]["fields"]["run_id"] == "run_retry_001"
    assert message is not None
    assert message.run_id == "run_retry_001"
    assert message.retry_reason == "worker_retry"
    assert message.retry_count == 1
    assert message.max_retries == 2


def test_redis_stream_run_queue_claims_pending_delivery_before_reading_new_messages() -> None:
    class FakeRedisStreamClient:
        def __init__(self) -> None:
            self.created_groups: list[dict[str, object]] = []
            self.autoclaim_calls: list[dict[str, object]] = []
            self.readgroup_calls: list[dict[str, object]] = []

        def xgroup_create(
            self,
            name: str,
            groupname: str,
            id: str,
            mkstream: bool,
        ) -> None:
            self.created_groups.append(
                {
                    "name": name,
                    "groupname": groupname,
                    "id": id,
                    "mkstream": mkstream,
                }
            )

        def xautoclaim(
            self,
            name: str,
            groupname: str,
            consumername: str,
            min_idle_time: int,
            start_id: str,
            count: int,
        ) -> tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]], list[bytes]]:
            self.autoclaim_calls.append(
                {
                    "name": name,
                    "groupname": groupname,
                    "consumername": consumername,
                    "min_idle_time": min_idle_time,
                    "start_id": start_id,
                    "count": count,
                }
            )
            return (
                b"0-0",
                [
                    (
                        b"1710000000000-0",
                        {
                            b"topic_id": b"topic_ai_agent",
                            b"trigger": b"scheduler",
                            b"run_id": b"run_pending_001",
                            b"enqueued_at": b"2026-06-09T12:00:00Z",
                            b"retry_reason": b"worker_retry",
                            b"retry_count": b"1",
                            b"max_retries": b"2",
                        },
                    )
                ],
                [],
            )

        def xreadgroup(
            self,
            groupname: str,
            consumername: str,
            streams: dict[str, str],
            count: int,
            block: int,
        ) -> list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]:
            self.readgroup_calls.append(
                {
                    "groupname": groupname,
                    "consumername": consumername,
                    "streams": streams,
                    "count": count,
                    "block": block,
                }
            )
            return [
                (
                    b"industry_news_agent:run_stream",
                    [
                        (
                            b"1710000000001-0",
                            {
                                b"topic_id": b"topic_ai_agent",
                                b"trigger": b"scheduler",
                                b"run_id": b"run_new_001",
                                b"enqueued_at": b"2026-06-09T12:10:00Z",
                            },
                        )
                    ],
                )
            ]

    client = FakeRedisStreamClient()
    queue = RedisStreamRunQueue(client)

    message = queue.dequeue()

    assert message is not None
    assert message.queue_message_id == "1710000000000-0"
    assert message.run_id == "run_pending_001"
    assert message.retry_reason == "worker_retry"
    assert client.autoclaim_calls == [
        {
            "name": "industry_news_agent:run_stream",
            "groupname": "monitor-workers",
            "consumername": "monitor-worker-1",
            "min_idle_time": 60000,
            "start_id": "0-0",
            "count": 1,
        }
    ]
    assert client.readgroup_calls == []


def test_run_queue_message_default_timestamp_is_per_instance() -> None:
    first = RunQueueMessage(topic_id="topic_001", trigger="scheduler")
    time.sleep(0.01)
    second = RunQueueMessage(topic_id="topic_001", trigger="scheduler")

    assert second.enqueued_at > first.enqueued_at


def test_tool_response_uses_uniform_success_and_failure_contract() -> None:
    success = ToolResponse.success(
        tool_name="mock_fetch",
        data={"items": ["alpha", "beta"]},
        summary="Fetched local mock items",
    )
    failure = ToolResponse.failure(
        tool_name="mock_fetch",
        code="tool_failed",
        message="Mock fetch failed",
        summary="Tool execution failed",
    )

    assert success.success is True
    assert success.error is None
    assert success.data == {"items": ["alpha", "beta"]}
    assert failure.success is False
    assert failure.data is None
    assert failure.error is not None
    assert failure.error.code == "tool_failed"


def test_tool_response_rejects_conflicting_success_and_error_state() -> None:
    with pytest.raises(ValueError, match="success=True"):
        ToolResponse(
            success=True,
            tool_name="mock_fetch",
            summary="Should reject inconsistent state",
            error=object(),
        )

    with pytest.raises(ValueError, match="success=False"):
        ToolResponse(
            success=False,
            tool_name="mock_fetch",
            summary="Should reject missing error state",
        )


def test_mock_llm_supports_keyword_expansion_article_extraction_and_scoring() -> None:
    client = MockLLM()

    expanded_keywords = client.expand_keywords(
        topic_name="AI Agent",
        seed_keywords=["OpenAI", "automation"],
    )
    extracted = client.extract_article(
        title="OpenAI ships an enterprise agent automation update",
        content=(
            "OpenAI released a new enterprise agent workflow. "
            "The update improves automation, reliability, and deployment guidance."
        ),
    )
    score = client.score_candidate(
        topic_name="AI Agent",
        candidate_title=extracted.title,
        candidate_summary=extracted.summary,
    )

    assert "openai" in expanded_keywords
    assert "ai agent" in expanded_keywords
    assert isinstance(extracted, ArticleExtractionResult)
    assert extracted.summary
    assert "automation" in extracted.keywords
    assert isinstance(score, CandidateScoreResult)
    assert 0.0 <= score.score <= 1.0
    assert score.score > 0.5


def test_mock_llm_expand_keywords_keeps_generator_inputs_stable() -> None:
    client = MockLLM()

    seed_keywords = (value for value in ["OpenAI", "automation"])
    expanded_keywords = client.expand_keywords(
        topic_name="AI Agent",
        seed_keywords=seed_keywords,
    )

    assert "openai" in expanded_keywords
    assert "automation" in expanded_keywords
    assert expanded_keywords.count("openai") == 1


def test_planner_agent_builds_context_aware_plan() -> None:
    from app.agent.planner_agent import PlannerAgent

    agent = PlannerAgent(llm=MockLLM())
    trusted_state = {
        "topic": {
            "name": "AI Agent Funding",
            "trusted_sources": ["techcrunch.com", "github.com"],
        },
        "business_memory": {
            "seed_keywords": ["AI Agent", "funding"],
            "business_context": {
                "documents": [
                    {"title": "Trusted sources improve push quality"},
                    {"title": "Funding events matter for this topic"},
                ]
            },
            "push_history": [{"title": "Previous funding alert"}],
            "trusted_sources": ["techcrunch.com", "github.com"],
        },
        "planner_output": {},
    }
    untrusted_state = {
        "topic": {
            "name": "AI Agent Funding",
            "trusted_sources": [],
        },
        "business_memory": {
            "seed_keywords": ["AI Agent", "funding"],
            "business_context": {"documents": []},
            "push_history": [],
            "trusted_sources": [],
        },
        "planner_output": {},
    }

    trusted_result = agent.run(trusted_state)
    untrusted_result = agent.run(untrusted_state)
    trusted_output = trusted_result["planner_output"]
    untrusted_output = untrusted_result["planner_output"]

    assert trusted_output["expanded_queries"]
    assert trusted_output["query_plan"]
    assert trusted_output["source_plan"]
    assert trusted_output["retrieval_strategy"]["mode"] == "rss_first"
    assert trusted_output["source_plan"][0]["tool_name"] == "rss_fetch"
    assert trusted_output["source_plan"][0]["trusted_sources"] == [
        "techcrunch.com",
        "github.com",
    ]
    assert trusted_output["planning_reasons"]

    assert untrusted_output["expanded_queries"]
    assert untrusted_output["query_plan"]
    assert untrusted_output["source_plan"]
    assert untrusted_output["retrieval_strategy"]["mode"] == "search_first"
    assert untrusted_output["source_plan"][0]["tool_name"] == "mock_search"
    assert untrusted_output["source_plan"][0].get("trusted_sources", []) == []
    assert untrusted_output["planning_reasons"]


def test_legacy_build_source_plan_keeps_tool_name_list_contract() -> None:
    from app.agent.planner import build_source_plan

    source_plan = build_source_plan(
        {
            "name": "AI Agent Funding",
            "trusted_sources": ["techcrunch.com", "github.com"],
        }
    )

    assert source_plan == ["rss_fetch", "mock_search"]


def test_plan_sources_node_populates_planner_output_and_legacy_source_plan() -> None:
    from app.agent.nodes import plan_sources_node

    state = {
        "topic": {
            "topic_id": "topic_ai_agent",
            "name": "AI Agent Funding",
            "trusted_sources": ["techcrunch.com", "github.com"],
        },
        "seed_keywords": ["AI Agent", "funding"],
        "business_context": {
            "documents": [
                {"title": "Trusted sources improve push quality"},
                {"title": "Funding events matter for this topic"},
            ]
        },
        "push_history": [{"title": "Previous funding alert"}],
        "expanded_queries": ["ai agent funding"],
        "planner_output": {},
        "events": [],
        "errors": [],
        "run_id": "run_001",
        "topic_id": "topic_ai_agent",
    }

    result = plan_sources_node(state)

    assert result["planner_output"]["source_plan"][0]["tool_name"] == "rss_fetch"
    assert result["planner_output"]["retrieval_strategy"]["mode"] == "rss_first"
    assert result["source_plan"] == ["rss_fetch", "mock_search"]


def test_plan_sources_node_preserves_existing_expanded_queries() -> None:
    from app.agent.nodes import plan_sources_node

    state = {
        "topic": {
            "topic_id": "topic_ai_agent",
            "name": "AI Agent Funding",
            "trusted_sources": ["techcrunch.com", "github.com"],
        },
        "seed_keywords": ["AI Agent", "funding"],
        "business_context": {
            "documents": [
                {"title": "Trusted sources improve push quality"},
            ]
        },
        "push_history": [{"title": "Previous funding alert"}],
        "expanded_queries": ["custom-expanded-query"],
        "planner_output": {},
        "events": [],
        "errors": [],
        "run_id": "run_001",
        "topic_id": "topic_ai_agent",
    }

    result = plan_sources_node(state)

    assert result["expanded_queries"] == ["custom-expanded-query"]
    assert result["planner_output"]["expanded_queries"] == ["custom-expanded-query"]


def test_knowledge_loader_and_keyword_retriever_support_local_rag() -> None:
    documents = load_knowledge_base(DEFAULT_KNOWLEDGE_BASE_PATH)
    retriever = KeywordRetriever(documents)

    results = retriever.retrieve("trusted source scoring", top_k=2)

    assert DEFAULT_KNOWLEDGE_BASE_PATH.exists()
    assert len(documents) >= 3
    assert len(results) == 2
    assert results[0].score >= results[1].score
    assert "source" in results[0].document.content.lower()


def test_knowledge_loader_reports_path_and_line_for_bad_jsonl(tmp_path: Path) -> None:
    knowledge_path = tmp_path / "broken_knowledge.jsonl"
    knowledge_path.write_text(
        json.dumps(
            {
                "doc_id": "kb_valid",
                "title": "Valid",
                "content": "Valid content",
                "keywords": ["valid"],
            }
        )
        + "\n"
        + '{"doc_id": "kb_broken", "title": "Broken"'
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="broken_knowledge.jsonl"):
        load_knowledge_base(knowledge_path)

    with pytest.raises(ValueError, match="line 2"):
        load_knowledge_base(knowledge_path)


def test_keyword_retriever_precomputes_document_tokens(monkeypatch) -> None:
    tokenize_calls: list[str] = []
    original_tokenize = keyword_retriever_module._tokenize

    def counting_tokenize(text: str) -> set[str]:
        tokenize_calls.append(text)
        return original_tokenize(text)

    documents = [
        KnowledgeDocument(
            doc_id="kb_001",
            title="Trusted source ranking",
            content="Trusted sources improve scoring quality.",
            keywords=["trusted", "source", "scoring"],
        ),
        KnowledgeDocument(
            doc_id="kb_002",
            title="Article extraction",
            content="Summaries keep evaluation concise.",
            keywords=["summary"],
        ),
    ]

    monkeypatch.setattr(keyword_retriever_module, "_tokenize", counting_tokenize)
    retriever = KeywordRetriever(documents)

    calls_after_init = len(tokenize_calls)
    retriever.retrieve("trusted source", top_k=1)
    retriever.retrieve("trusted source", top_k=1)

    assert calls_after_init == len(documents)
    assert len(tokenize_calls) == len(documents) + 2


def test_bm25_retriever_ranks_term_frequency_with_length_normalization() -> None:
    documents = [
        KnowledgeDocument(
            doc_id="kb_short_relevant",
            title="Trusted source ranking",
            content="Trusted source ranking improves news quality.",
            keywords=["trusted", "source", "ranking"],
        ),
        KnowledgeDocument(
            doc_id="kb_long_repetitive",
            title="Trusted source ranking",
            content=(
                "trusted source ranking " * 3
                + "generic filler " * 80
            ),
            keywords=["trusted"],
        ),
        KnowledgeDocument(
            doc_id="kb_irrelevant",
            title="Article extraction",
            content="Summaries and extraction are separate concerns.",
            keywords=["summary"],
        ),
    ]

    results = BM25Retriever(documents).retrieve("trusted source ranking", top_k=2)

    assert [result.document.doc_id for result in results] == [
        "kb_short_relevant",
        "kb_long_repetitive",
    ]
    assert results[0].score > results[1].score
    assert all(result.metadata["retriever"] == "bm25" for result in results)


def test_local_vector_retriever_uses_cosine_similarity_over_document_terms() -> None:
    documents = [
        KnowledgeDocument(
            doc_id="kb_source_quality",
            title="Trusted source quality",
            content="Trusted domains improve source quality for industry monitoring.",
            keywords=["trusted", "source", "quality"],
        ),
        KnowledgeDocument(
            doc_id="kb_scoring",
            title="Scoring pipeline",
            content="Relevance scoring combines business value and evidence quality.",
            keywords=["scoring", "business", "evidence"],
        ),
        KnowledgeDocument(
            doc_id="kb_extract",
            title="Article extraction",
            content="Extraction creates concise summaries and normalized keywords.",
            keywords=["summary", "keywords"],
        ),
    ]

    results = LocalVectorRetriever(documents).retrieve(
        "trusted source quality",
        top_k=2,
    )

    assert [result.document.doc_id for result in results] == [
        "kb_source_quality",
        "kb_scoring",
    ]
    assert results[0].score > results[1].score
    assert all(result.metadata["retriever"] == "embedding_like" for result in results)


def test_hybrid_retriever_returns_reranked_multi_route_context() -> None:
    documents = [
        KnowledgeDocument(
            doc_id="kb_source_quality",
            title="Trusted source quality",
            content="Trusted domains improve source quality for industry monitoring.",
            keywords=["trusted", "source", "quality"],
        ),
        KnowledgeDocument(
            doc_id="kb_business_value",
            title="Business value scoring",
            content="Business value and evidence quality improve candidate scoring.",
            keywords=["business", "scoring", "evidence"],
        ),
    ]

    context = retrieve_hybrid_context(
        documents,
        "trusted source quality",
        top_k=2,
    )

    assert context["retrieval_mode"] == "hybrid_keyword_bm25_embedding_rerank"
    assert context["retrievers"] == ["keyword", "bm25", "embedding_like"]
    assert context["documents"][0]["doc_id"] == "kb_source_quality"
    assert context["documents"][0]["rerank_score"] >= context["documents"][1]["rerank_score"]
    assert "embedding_like" in context["documents"][0]["scores"]


def test_local_tool_gateway_registers_and_calls_local_tools() -> None:
    gateway = LocalToolGateway()

    def echo_tool(text: str) -> ToolResponse:
        return ToolResponse.success(
            tool_name="echo",
            data={"echo": text},
            summary="Echo tool completed",
        )

    gateway.register("echo", echo_tool)
    response = gateway.call("echo", text="industry-news")

    assert response.success is True
    assert response.data == {"echo": "industry-news"}
    assert response.summary == "Echo tool completed"


def test_local_tool_gateway_wraps_missing_tools_and_tool_errors() -> None:
    gateway = LocalToolGateway()

    def broken_tool() -> ToolResponse:
        raise RuntimeError("boom")

    def invalid_tool() -> object:
        return {"unexpected": "value"}

    gateway.register("broken", broken_tool)
    gateway.register("invalid", invalid_tool)

    missing = gateway.call("missing")
    broken = gateway.call("broken")
    invalid = gateway.call("invalid")

    assert missing.success is False
    assert missing.error is not None
    assert missing.error.code == "tool_not_registered"
    assert broken.success is False
    assert broken.error is not None
    assert broken.error.code == "tool_execution_failed"
    assert invalid.success is False
    assert invalid.error is not None
    assert invalid.error.code == "invalid_tool_response"


def _build_task6_topic() -> dict[str, object]:
    return {
        "topic_id": "topic_ai_agent",
        "name": "AI Agent",
        "description": "Track enterprise AI agent launches and deployment updates.",
        "seed_keywords": ["OpenAI", "enterprise", "automation"],
        "trusted_sources": ["AI Daily RSS", "AI Search"],
        "exclude_keywords": ["rumor"],
        "push_threshold": 0.72,
    }


def test_task6_tool_registry_registers_minimal_candidate_pipeline() -> None:
    from app.tools.registry import build_default_tool_registry

    registry = build_default_tool_registry(llm=MockLLM())
    gateway = LocalToolGateway()
    registry.register_into(gateway)

    assert registry.list_tool_names() == [
        "rss_fetch",
        "mock_search",
        "search_news",
        "fetch_article_content",
        "extract_article",
        "deduplicate_items",
        "score_candidate",
        "decide_push",
        "notification_send",
    ]

    response = gateway.call(
        "rss_fetch",
        run_id="run_task6_registry",
        topic=_build_task6_topic(),
    )

    assert response.success is True
    assert response.error is None
    assert response.data is not None
    assert response.data["run_id"] == "run_task6_registry"
    assert len(response.data["candidates"]) == 1
    assert response.data["candidates"][0]["source_type"] == "rss"


def test_task6_pipeline_supports_fixture_retrieval_extract_dedup_score_and_push() -> None:
    from app.tools.registry import build_default_tool_registry

    topic = _build_task6_topic()
    registry = build_default_tool_registry(llm=MockLLM())
    gateway = LocalToolGateway()
    registry.register_into(gateway)

    rss_response = gateway.call("rss_fetch", run_id="run_task6_chain", topic=topic)
    search_response = gateway.call(
        "mock_search",
        run_id="run_task6_chain",
        topic=topic,
    )

    assert rss_response.success is True
    assert search_response.success is True
    assert rss_response.data is not None
    assert search_response.data is not None

    candidates = [
        *rss_response.data["candidates"],
        *search_response.data["candidates"],
    ]

    assert len(candidates) == 3

    fetch_response = gateway.call("fetch_article_content", candidates=candidates)

    assert fetch_response.success is True
    assert fetch_response.data is not None
    fetched_candidates = fetch_response.data["candidates"]
    assert all(item["fetch_status"] == "fetched" for item in fetched_candidates)
    assert all(item["content"] for item in fetched_candidates)

    extract_response = gateway.call(
        "extract_article",
        run_id="run_task6_chain",
        topic=topic,
        candidates=fetched_candidates,
    )

    assert extract_response.success is True
    assert extract_response.data is not None
    extracted_articles = extract_response.data["articles"]
    assert len(extracted_articles) == 3
    assert extracted_articles[0]["summary"]
    assert extracted_articles[0]["keywords"]

    dedup_response = gateway.call("deduplicate_items", articles=extracted_articles)

    assert dedup_response.success is True
    assert dedup_response.data is not None
    deduped_articles = dedup_response.data["articles"]
    assert len(deduped_articles) == 2
    assert dedup_response.data["deduped_count"] == 2
    assert dedup_response.data["dropped_candidate_ids"] == ["cand_search_openai_dup"]

    score_response = gateway.call(
        "score_candidate",
        topic=topic,
        articles=deduped_articles,
    )

    assert score_response.success is True
    assert score_response.data is not None
    scored_articles = score_response.data["articles"]
    assert len(scored_articles) == 2

    openai_article = next(
        item for item in scored_articles if item["candidate_id"] == "cand_rss_openai"
    )
    rumor_article = next(
        item for item in scored_articles if item["candidate_id"] == "cand_search_rumor"
    )

    assert openai_article["score"] >= topic["push_threshold"]
    assert rumor_article["score"] < topic["push_threshold"]
    assert "trusted source" in openai_article["score_breakdown"]
    assert "exclude keyword" in rumor_article["score_breakdown"]

    push_response = gateway.call(
        "decide_push",
        run_id="run_task6_chain",
        topic=topic,
        articles=scored_articles,
    )

    assert push_response.success is True
    assert push_response.data is not None
    pushes = push_response.data["pushes"]
    assert len(pushes) == 2
    assert push_response.data["push_count"] == 1
    assert sum(1 for push in pushes if push["should_push"]) == 1

    push_by_candidate_id = {push["candidate_id"]: push for push in pushes}
    assert push_by_candidate_id["cand_rss_openai"]["should_push"] is True
    assert push_by_candidate_id["cand_search_rumor"]["should_push"] is False
    assert "below threshold" in push_by_candidate_id["cand_search_rumor"]["decision_reason"]


def test_task6_dedup_uses_content_fingerprint_in_addition_to_url_and_title() -> None:
    from app.tools.registry import build_default_tool_registry

    registry = build_default_tool_registry(llm=MockLLM())
    gateway = LocalToolGateway()
    registry.register_into(gateway)

    articles = [
        {
            "candidate_id": "cand_a",
            "title": "OpenAI launches AI agent automation workflow for enterprises",
            "url": "https://example.com/articles/openai-ai-agent-workflow",
            "summary": "Enterprise workflow launch.",
            "content": "Alpha version of the article body.",
        },
        {
            "candidate_id": "cand_b",
            "title": "OpenAI launches AI agent automation workflow for enterprises",
            "url": "https://another.example.com/articles/openai-ai-agent-workflow",
            "summary": "Enterprise workflow launch from another source.",
            "content": "Beta version with materially different body text.",
        },
        {
            "candidate_id": "cand_c",
            "title": "OpenAI launches AI agent automation workflow for enterprises",
            "url": "https://another.example.com/articles/openai-ai-agent-workflow?utm_source=dup",
            "summary": "Exact duplicate body from another source path variant.",
            "content": "Beta version with materially different body text.",
        },
    ]

    dedup_response = gateway.call("deduplicate_items", articles=articles)

    assert dedup_response.success is True
    assert dedup_response.data is not None
    kept_articles = dedup_response.data["articles"]
    assert [article["candidate_id"] for article in kept_articles] == ["cand_a", "cand_b"]
    assert dedup_response.data["dropped_candidate_ids"] == ["cand_c"]
    assert dedup_response.data["drop_reasons"]["cand_c"] == {
        "reason": "exact_duplicate",
        "matched_key": "canonical_url_normalized_title_content_fingerprint",
    }
    assert dedup_response.data["semantic_dropped_candidate_ids"] == []
    assert dedup_response.data["semantic_drop_reasons"] == {}
    assert dedup_response.metadata["semantic_dedup_provider"] is None


def test_local_semantic_dedup_drops_similar_title_and_summary() -> None:
    from app.tools.semantic_dedup import LocalSemanticDedupStrategy

    strategy = LocalSemanticDedupStrategy(threshold=0.55)
    articles = [
        {
            "candidate_id": "cand_a",
            "title": "OpenAI launches enterprise agent workflow",
            "summary": "OpenAI released an enterprise agent automation workflow.",
        },
        {
            "candidate_id": "cand_b",
            "title": "OpenAI releases enterprise agent workflow",
            "summary": "OpenAI launched an enterprise workflow for agent automation.",
        },
        {
            "candidate_id": "cand_c",
            "title": "Chip startup raises new funding",
            "summary": "A semiconductor startup announced funding.",
        },
    ]

    result = strategy.deduplicate(articles)

    assert [item["candidate_id"] for item in result.kept_articles] == ["cand_a", "cand_c"]
    assert result.dropped_candidate_ids == ["cand_b"]
    assert result.drop_reasons["cand_b"]["reason"] == "semantic_similarity"
    assert result.drop_reasons["cand_b"]["matched_candidate_id"] == "cand_a"


def test_dedup_tool_applies_semantic_strategy_after_exact_dedup() -> None:
    from app.tools.dedup_tool import DedupCandidatesTool
    from app.tools.semantic_dedup import LocalSemanticDedupStrategy

    tool = DedupCandidatesTool(
        semantic_strategy=LocalSemanticDedupStrategy(threshold=0.55)
    )

    response = tool(
        articles=[
            {
                "candidate_id": "cand_a",
                "title": "OpenAI launches enterprise agent workflow",
                "url": "https://example.com/a",
                "summary": "OpenAI released an enterprise agent automation workflow.",
                "content": "OpenAI released an enterprise agent automation workflow.",
            },
            {
                "candidate_id": "cand_b",
                "title": "OpenAI releases enterprise agent workflow",
                "url": "https://example.com/b",
                "summary": "OpenAI launched an enterprise workflow for agent automation.",
                "content": "OpenAI launched an enterprise workflow for agent automation.",
            },
        ],
    )

    assert response.data is not None
    assert [item["candidate_id"] for item in response.data["articles"]] == ["cand_a"]
    assert response.data["dropped_candidate_ids"] == ["cand_b"]
    assert response.data["semantic_dropped_candidate_ids"] == ["cand_b"]
    assert response.metadata["semantic_dedup_provider"] == "local"


def test_build_default_tool_registry_enables_local_semantic_dedup() -> None:
    from app.tools.registry import build_default_tool_registry

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        semantic_dedup_provider="local",
        semantic_dedup_threshold=0.55,
    )
    registry = build_default_tool_registry(llm=MockLLM(), settings=settings)
    gateway = LocalToolGateway()
    registry.register_into(gateway)

    response = gateway.call(
        "deduplicate_items",
        articles=[
            {
                "candidate_id": "cand_a",
                "title": "OpenAI launches enterprise agent workflow",
                "url": "https://example.com/a",
                "summary": "OpenAI released an enterprise agent automation workflow.",
                "content": "OpenAI released an enterprise agent automation workflow.",
            },
            {
                "candidate_id": "cand_b",
                "title": "OpenAI releases enterprise agent workflow",
                "url": "https://example.com/b",
                "summary": "OpenAI launched an enterprise workflow for agent automation.",
                "content": "OpenAI launched an enterprise workflow for agent automation.",
            },
        ],
    )

    assert response.data is not None
    assert response.metadata["semantic_dedup_provider"] == "local"
    assert response.data["semantic_dropped_candidate_ids"] == ["cand_b"]


def test_build_default_tool_registry_keeps_semantic_dedup_disabled_by_default() -> None:
    from app.tools.registry import build_default_tool_registry

    registry = build_default_tool_registry(llm=MockLLM())
    gateway = LocalToolGateway()
    registry.register_into(gateway)

    response = gateway.call(
        "deduplicate_items",
        articles=[
            {
                "candidate_id": "cand_a",
                "title": "OpenAI launches enterprise agent workflow",
                "url": "https://example.com/a",
                "summary": "OpenAI released an enterprise agent automation workflow.",
                "content": "OpenAI released an enterprise agent automation workflow.",
            },
            {
                "candidate_id": "cand_b",
                "title": "OpenAI releases enterprise agent workflow",
                "url": "https://example.com/b",
                "summary": "OpenAI launched an enterprise workflow for agent automation.",
                "content": "OpenAI launched an enterprise workflow for agent automation.",
            },
        ],
    )

    assert response.data is not None
    assert [item["candidate_id"] for item in response.data["articles"]] == [
        "cand_a",
        "cand_b",
    ]
    assert response.data["semantic_dropped_candidate_ids"] == []
    assert response.data["semantic_drop_reasons"] == {}
    assert response.metadata["semantic_dedup_provider"] is None


def test_semantic_dedup_missing_candidate_id_returns_tool_failure() -> None:
    from app.tools.registry import build_default_tool_registry

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        semantic_dedup_provider="local",
    )
    registry = build_default_tool_registry(llm=MockLLM(), settings=settings)
    gateway = LocalToolGateway()
    registry.register_into(gateway)

    response = gateway.call(
        "deduplicate_items",
        articles=[
            {
                "title": "OpenAI launches enterprise agent workflow",
                "url": "https://example.com/a",
                "summary": "OpenAI released an enterprise agent automation workflow.",
            },
        ],
    )

    assert response.success is False
    assert response.error is not None
    assert response.error.code == "tool_execution_failed"
    assert "candidate_id" in response.error.message


def test_task6_extract_degrades_to_raw_summary_mode_when_fetch_fails() -> None:
    from app.tools.registry import build_default_tool_registry

    topic = _build_task6_topic()
    registry = build_default_tool_registry(llm=MockLLM())
    gateway = LocalToolGateway()
    registry.register_into(gateway)

    extract_response = gateway.call(
        "extract_article",
        run_id="run_task6_summary_mode",
        topic=topic,
        candidates=[
            {
                "candidate_id": "cand_failed_fetch",
                "run_id": "run_task6_summary_mode",
                "topic_id": topic["topic_id"],
                "source_type": "search",
                "source_name": "AI Search",
                "title": "OpenAI enterprise agent update reaches summary fallback",
                "url": "https://example.com/articles/openai-summary-fallback",
                "published_at": "2026-06-08T12:00:00Z",
                "raw_summary": "Fallback summary from search results.",
                "fetch_status": "failed",
                "fetch_error": "timeout",
                "content": "",
            }
        ],
    )

    assert extract_response.success is True
    assert extract_response.data is not None
    assert extract_response.data["skipped_candidate_ids"] == []

    extracted_articles = extract_response.data["articles"]
    assert len(extracted_articles) == 1
    extracted_article = extracted_articles[0]
    assert extracted_article["candidate_id"] == "cand_failed_fetch"
    assert extracted_article["summary"] == "Fallback summary from search results."
    assert extracted_article["content"] == ""
    assert extracted_article["extraction_mode"] == "raw_summary"
    assert extracted_article["fetch_status"] == "failed"
    assert extracted_article["fetch_error"] == "timeout"


def test_build_default_tool_registry_uses_open_websearch_provider_when_enabled() -> None:
    from app.core.config import Settings
    from app.tools.registry import build_default_tool_registry

    class FakeOpenWebSearchResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "results": [
                    {
                        "title": "OpenAI ships enterprise agent workflow",
                        "url": "https://example.com/openai-agent-workflow",
                        "content": "Enterprise agent automation update.",
                        "publishedDate": "2026-06-08T10:00:00Z",
                    }
                ]
            }

    class FakeOpenWebSearchClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def get(self, url: str, **kwargs: object) -> FakeOpenWebSearchResponse:
            self.requests.append({"url": url, **kwargs})
            return FakeOpenWebSearchResponse()

    http_client = FakeOpenWebSearchClient()
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        search_provider="open_websearch",
        open_websearch_base_url="http://localhost:8080",
    )

    registry = build_default_tool_registry(
        llm=MockLLM(),
        settings=settings,
        search_http_client=http_client,
    )

    assert "search_news" in registry.list_tool_names()
    assert "mock_search" in registry.list_tool_names()

    gateway = LocalToolGateway()
    registry.register_into(gateway)

    response = gateway.call(
        "search_news",
        run_id="run_task6_real_search",
        topic=_build_task6_topic(),
    )

    assert response.success is True
    assert response.data is not None
    assert response.data["candidates"][0]["source_name"] == "OpenWebSearch"
    assert response.metadata["provider"] == "open_websearch"
    assert response.metadata["used_fallback"] is False
    assert http_client.requests[0]["url"] == "http://localhost:8080/search"


def test_onesearch_gateway_calls_wrapper_and_maps_results() -> None:
    from app.mcp.local_gateway import LocalToolGateway
    from app.mcp.onesearch_gateway import OneSearchMCPGateway
    from app.tools.responses import ToolResponse

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "results": [
                    {
                        "title": "OpenAI ships enterprise agent workflow",
                        "url": "https://example.com/agent-workflow",
                        "snippet": "Enterprise workflow update.",
                        "source": "example.com",
                        "published_at": "2026-06-17T10:00:00Z",
                    }
                ]
            }

    class FakeHttpClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def post(self, url: str, **kwargs: object) -> FakeResponse:
            self.requests.append({"url": url, **kwargs})
            return FakeResponse()

    http_client = FakeHttpClient()
    fallback_gateway = LocalToolGateway()
    fallback_gateway.register(
        "fetch_article_content",
        lambda **kwargs: ToolResponse.success(
            tool_name="fetch_article_content",
            summary="local fetch",
            data={"candidates": []},
        ),
    )
    gateway = OneSearchMCPGateway(
        base_url="http://localhost:8090",
        http_client=http_client,
        fallback_gateway=fallback_gateway,
        timeout_seconds=4.0,
        max_results=5,
    )

    response = gateway.call(
        "search_news",
        run_id="run_onesearch_001",
        topic={
            "topic_id": "topic_ai_agent",
            "name": "AI Agent",
            "seed_keywords": ["OpenAI", "enterprise"],
        },
    )

    assert response.success is True
    assert response.data is not None
    assert response.data["candidates"][0]["source_name"] == "example.com"
    assert response.metadata["provider"] == "onesearch_mcp"
    assert response.metadata["used_fallback"] is False
    assert http_client.requests[0]["url"] == "http://localhost:8090/search"
    assert http_client.requests[0]["json"] == {
        "query": "AI Agent OpenAI enterprise",
        "max_results": 5,
    }
    assert http_client.requests[0]["timeout"] == 4.0


def test_onesearch_gateway_falls_back_to_local_mock_search_when_provider_fails() -> None:
    from app.mcp.local_gateway import LocalToolGateway
    from app.mcp.onesearch_gateway import OneSearchMCPGateway
    from app.tools.responses import ToolResponse

    class FailingHttpClient:
        def post(self, url: str, **kwargs: object) -> object:
            raise RuntimeError("onesearch unavailable")

    fallback_gateway = LocalToolGateway()
    fallback_gateway.register(
        "search_news",
        lambda run_id, topic: ToolResponse.success(
            tool_name="search_news",
            summary="Used local mock search fallback.",
            data={
                "run_id": run_id,
                "candidates": [
                    {
                        "candidate_id": "cand_local_001",
                        "run_id": run_id,
                        "topic_id": topic["topic_id"],
                        "source_type": "search",
                        "source_name": "AI Search",
                        "title": "Fallback item",
                        "url": "https://example.com/fallback",
                        "published_at": None,
                        "raw_summary": "Fallback summary",
                        "fetch_status": "pending",
                    }
                ],
            },
            metadata={
                "provider": "mock_search",
                "used_fallback": False,
            },
        ),
    )
    gateway = OneSearchMCPGateway(
        base_url="http://localhost:8090",
        http_client=FailingHttpClient(),
        fallback_gateway=fallback_gateway,
        timeout_seconds=4.0,
        max_results=5,
    )

    response = gateway.call(
        "search_news",
        run_id="run_onesearch_fallback",
        topic={
            "topic_id": "topic_ai_agent",
            "name": "AI Agent",
            "seed_keywords": ["OpenAI", "enterprise"],
        },
    )

    assert response.success is True
    assert response.metadata["provider"] == "onesearch_mcp"
    assert response.metadata["fallback_provider"] == "mock_search"
    assert response.metadata["used_fallback"] is True
    assert response.metadata["fallback_reason"] == "onesearch unavailable"
    assert response.data is not None
    assert response.data["candidates"][0]["title"] == "Fallback item"


def test_onesearch_gateway_delegates_non_search_tools_to_fallback_gateway() -> None:
    from app.mcp.local_gateway import LocalToolGateway
    from app.mcp.onesearch_gateway import OneSearchMCPGateway
    from app.tools.responses import ToolResponse

    fallback_gateway = LocalToolGateway()
    fallback_gateway.register(
        "fetch_article_content",
        lambda **kwargs: ToolResponse.success(
            tool_name="fetch_article_content",
            summary="delegated",
            data={"candidates": [{"candidate_id": "cand_001"}]},
            metadata={"provider": "local_gateway"},
        ),
    )
    gateway = OneSearchMCPGateway(
        base_url="http://localhost:8090",
        fallback_gateway=fallback_gateway,
    )

    response = gateway.call(
        "fetch_article_content",
        candidates=[{"candidate_id": "cand_001"}],
    )

    assert response.success is True
    assert response.summary == "delegated"
    assert response.data == {"candidates": [{"candidate_id": "cand_001"}]}


def test_build_monitor_graph_uses_local_gateway_by_default() -> None:
    from app.agent.graph import _build_default_gateway
    from app.mcp.local_gateway import LocalToolGateway

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
    )

    gateway = _build_default_gateway(MockLLM(), settings)

    assert isinstance(gateway, LocalToolGateway)


def test_build_monitor_graph_uses_onesearch_gateway_when_configured() -> None:
    from app.agent.graph import _build_default_gateway
    from app.mcp.onesearch_gateway import OneSearchMCPGateway

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        mcp_gateway_provider="onesearch",
        onesearch_base_url="http://localhost:8090",
    )

    gateway = _build_default_gateway(MockLLM(), settings)

    assert isinstance(gateway, OneSearchMCPGateway)


def test_build_monitor_graph_degrades_to_local_gateway_when_onesearch_config_is_incomplete() -> None:
    from app.agent.graph import _build_default_gateway
    from app.mcp.local_gateway import LocalToolGateway

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        mcp_gateway_provider="onesearch",
        onesearch_base_url=None,
    )

    gateway = _build_default_gateway(MockLLM(), settings)

    assert isinstance(gateway, LocalToolGateway)


def test_task6_search_provider_falls_back_to_mock_when_real_provider_fails() -> None:
    from app.core.config import Settings
    from app.tools.registry import build_default_tool_registry

    class FailingOpenWebSearchClient:
        def get(self, url: str, **kwargs: object) -> object:
            raise RuntimeError("open-websearch unavailable")

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        search_provider="open_websearch",
        open_websearch_base_url="http://localhost:8080",
    )

    registry = build_default_tool_registry(
        llm=MockLLM(),
        settings=settings,
        search_http_client=FailingOpenWebSearchClient(),
    )
    gateway = LocalToolGateway()
    registry.register_into(gateway)

    response = gateway.call(
        "search_news",
        run_id="run_task6_real_search_fallback",
        topic=_build_task6_topic(),
    )

    assert response.metadata["provider"] == "open_websearch"
    assert response.metadata["fallback_provider"] == "mock_search"
    assert response.metadata["used_fallback"] is True
    assert response.success is True
    assert response.data is not None
    assert len(response.data["candidates"]) == 2


def test_build_default_tool_registry_wires_playwright_mcp_browser_fallback() -> None:
    from app.core.config import Settings
    from app.tools.registry import build_default_tool_registry

    class FakeBrowserResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"content": "dynamic browser content"}

    class FakeBrowserClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def post(self, url: str, **kwargs: object) -> FakeBrowserResponse:
            self.requests.append({"url": url, **kwargs})
            return FakeBrowserResponse()

    class FailingHTTPClient:
        def get(self, url: str, **kwargs: object) -> object:
            raise RuntimeError("plain http failed")

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        browser_fetch_provider="playwright_mcp",
        playwright_mcp_base_url="http://localhost:8931",
        browser_allowed_domains=["example.com"],
    )
    browser_client = FakeBrowserClient()
    registry = build_default_tool_registry(
        llm=MockLLM(),
        settings=settings,
        fetch_http_client=FailingHTTPClient(),
        browser_http_client=browser_client,
    )
    gateway = LocalToolGateway()
    registry.register_into(gateway)

    response = gateway.call(
        "fetch_article_content",
        candidates=[
            {
                "candidate_id": "cand_dynamic",
                "url": "https://example.com/articles/dynamic",
                "raw_summary": "Dynamic summary",
            }
        ],
    )

    assert response.success is True
    assert response.data is not None
    candidate = response.data["candidates"][0]
    assert candidate["fetch_status"] == "fetched"
    assert candidate["fetch_method"] == "browser_fallback"
    assert candidate["content"] == "dynamic browser content"
    assert response.metadata["used_browser_fallback"] is True
    assert response.metadata["browser_provider"] == "playwright_mcp"
    assert browser_client.requests[0]["url"] == "http://localhost:8931/fetch"


def test_browser_fetch_tool_marks_browser_fallback_when_http_fetch_fails() -> None:
    from app.tools.browser_fetch_tool import BrowserFetchTool

    def failing_fetcher(url: str) -> str:
        raise RuntimeError(f"http failed for {url}")

    def browser_fetcher(url: str) -> str:
        return f"browser content for {url}"

    tool = BrowserFetchTool(
        fetcher=failing_fetcher,
        browser_fetcher=browser_fetcher,
    )

    response = tool(
        candidates=[
            {
                "candidate_id": "cand_browser_fallback",
                "url": "https://example.com/articles/browser-fallback",
                "raw_summary": "Fallback summary",
            }
        ]
    )

    assert response.success is True
    assert response.data is not None
    candidate = response.data["candidates"][0]
    assert candidate["fetch_status"] == "fetched"
    assert candidate["content"] == "browser content for https://example.com/articles/browser-fallback"
    assert candidate["fetch_method"] == "browser_fallback"
    assert candidate["fetch_fallback_reason"] == (
        "http failed for https://example.com/articles/browser-fallback"
    )
    assert response.metadata["used_browser_fallback"] is True


def test_browser_fetch_tool_does_not_use_browser_when_http_fetch_succeeds() -> None:
    from app.tools.browser_fetch_tool import BrowserFetchTool

    calls: list[str] = []

    def http_fetcher(url: str) -> str:
        return f"http content for {url}"

    def browser_fetcher(url: str) -> str:
        calls.append(url)
        return "browser content"

    tool = BrowserFetchTool(
        fetcher=http_fetcher,
        browser_fetcher=browser_fetcher,
        browser_provider="playwright_mcp",
    )

    response = tool(
        candidates=[
            {
                "candidate_id": "cand_http_first",
                "url": "https://example.com/articles/http-first",
                "raw_summary": "HTTP summary",
            }
        ]
    )

    assert response.success is True
    assert response.data is not None
    candidate = response.data["candidates"][0]
    assert candidate["fetch_status"] == "fetched"
    assert candidate["fetch_method"] == "http"
    assert candidate["content"] == (
        "http content for https://example.com/articles/http-first"
    )
    assert calls == []
    assert response.metadata["used_browser_fallback"] is False


def test_playwright_mcp_browser_fetcher_calls_allowed_domain_and_truncates() -> None:
    from app.tools.browser_fetch_tool import PlaywrightMCPBrowserFetcher

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"content": "abcdef"}

    class FakeClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def post(self, url: str, **kwargs: object) -> FakeResponse:
            self.requests.append({"url": url, **kwargs})
            return FakeResponse()

    client = FakeClient()
    fetcher = PlaywrightMCPBrowserFetcher(
        base_url="http://localhost:8931",
        allowed_domains=["example.com"],
        http_client=client,
        timeout_seconds=3.0,
        max_content_chars=4,
    )

    content = fetcher("https://example.com/articles/dynamic")

    assert content == "abcd"
    assert client.requests[0]["url"] == "http://localhost:8931/fetch"
    assert client.requests[0]["json"] == {"url": "https://example.com/articles/dynamic"}
    assert client.requests[0]["timeout"] == 3.0


def test_playwright_mcp_browser_fetcher_rejects_disallowed_domain() -> None:
    from app.tools.browser_fetch_tool import PlaywrightMCPBrowserFetcher

    fetcher = PlaywrightMCPBrowserFetcher(
        base_url="http://localhost:8931",
        allowed_domains=["example.com"],
    )

    with pytest.raises(ValueError, match="not allowed"):
        fetcher("https://evil.example.net/story")


def test_playwright_mcp_browser_fetcher_limits_concurrent_calls() -> None:
    from app.tools.browser_fetch_tool import PlaywrightMCPBrowserFetcher

    class SlowResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"content": "browser content"}

    class SlowClient:
        def __init__(self) -> None:
            self.active_calls = 0
            self.max_active_calls = 0
            self.first_call_entered = Event()
            self.release_first_call = Event()
            self.lock = Lock()

        def post(self, url: str, **kwargs: object) -> SlowResponse:
            with self.lock:
                self.active_calls += 1
                self.max_active_calls = max(self.max_active_calls, self.active_calls)
                is_first_call = not self.first_call_entered.is_set()
                if is_first_call:
                    self.first_call_entered.set()
            if is_first_call:
                assert self.release_first_call.wait(timeout=1.0)
            with self.lock:
                self.active_calls -= 1
            return SlowResponse()

    client = SlowClient()
    fetcher = PlaywrightMCPBrowserFetcher(
        base_url="http://localhost:8931",
        allowed_domains=["example.com"],
        http_client=client,
        max_concurrency=1,
    )
    results: list[str] = []
    errors: list[BaseException] = []

    def fetch_in_thread(url: str) -> None:
        try:
            results.append(fetcher(url))
        except BaseException as exc:
            errors.append(exc)

    first_thread = Thread(
        target=fetch_in_thread,
        args=("https://example.com/first",),
    )
    second_thread = Thread(
        target=fetch_in_thread,
        args=("https://example.com/second",),
    )

    first_thread.start()
    assert client.first_call_entered.wait(timeout=1.0)
    second_thread.start()
    time.sleep(0.05)
    client.release_first_call.set()
    first_thread.join(timeout=1.0)
    second_thread.join(timeout=1.0)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert errors == []
    assert sorted(results) == ["browser content", "browser content"]
    assert client.max_active_calls == 1


def test_opensearch_history_index_posts_candidate_documents() -> None:
    from app.search.history_index import OpenSearchHistoryIndex

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def put(self, url: str, **kwargs: object) -> FakeResponse:
            self.requests.append({"url": url, **kwargs})
            return FakeResponse()

    client = FakeClient()
    index = OpenSearchHistoryIndex(
        base_url="http://localhost:9200",
        index_name="industry-news-candidates",
        http_client=client,
        timeout_seconds=3.0,
    )

    result = index.index_candidates(
        [
            {
                "candidate_id": "cand_001",
                "run_id": "run_001",
                "topic_id": "topic_ai",
                "source_type": "search",
                "source_name": "OpenWebSearch",
                "title": "OpenAI ships agent workflow",
                "url": "https://example.com/agent",
                "raw_summary": "Agent workflow update.",
                "content": "Full article body.",
                "score": 0.91,
                "decision": "push",
                "decision_reason": "Above threshold",
            }
        ]
    )

    assert result == {"indexed_count": 1, "provider": "opensearch"}
    assert client.requests[0]["url"] == (
        "http://localhost:9200/industry-news-candidates/_doc/run_001-cand_001"
    )
    assert client.requests[0]["timeout"] == 3.0
    assert client.requests[0]["json"]["title"] == "OpenAI ships agent workflow"
    assert client.requests[0]["json"]["content"] == "Full article body."


def test_opensearch_history_index_serializes_datetime_and_quotes_document_id() -> None:
    from app.search.history_index import OpenSearchHistoryIndex

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def put(self, url: str, **kwargs: object) -> FakeResponse:
            self.requests.append({"url": url, **kwargs})
            return FakeResponse()

    client = FakeClient()
    index = OpenSearchHistoryIndex(
        base_url="http://localhost:9200",
        index_name="industry-news-candidates",
        http_client=client,
    )

    index.index_candidates(
        [
            {
                "candidate_id": "cand/001",
                "run_id": "run 001",
                "topic_id": "topic_ai",
                "title": "OpenAI ships agent workflow",
                "url": "https://example.com/agent",
                "created_at": datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
            }
        ]
    )

    assert client.requests[0]["url"] == (
        "http://localhost:9200/industry-news-candidates/_doc/run%20001-cand%2F001"
    )
    assert client.requests[0]["json"]["created_at"] == "2026-06-09T12:00:00Z"


def test_opensearch_history_index_can_search_candidate_documents() -> None:
    from app.search.history_index import OpenSearchHistoryIndex

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self.payload

    class FakeClient:
        def __init__(self) -> None:
            self.put_requests: list[dict[str, object]] = []
            self.post_requests: list[dict[str, object]] = []

        def put(self, url: str, **kwargs: object) -> FakeResponse:
            self.put_requests.append({"url": url, **kwargs})
            return FakeResponse({"result": "created"})

        def post(self, url: str, **kwargs: object) -> FakeResponse:
            self.post_requests.append({"url": url, **kwargs})
            return FakeResponse(
                {
                    "hits": {
                        "hits": [
                            {
                                "_source": {
                                    "candidate_id": "cand_001",
                                    "title": "OpenAI agent update",
                                    "topic_id": "topic_ai",
                                }
                            }
                        ]
                    }
                }
            )

    client = FakeClient()
    index = OpenSearchHistoryIndex(
        base_url="http://localhost:9200",
        index_name="industry-news-candidates",
        http_client=client,
        timeout_seconds=3.0,
    )

    search_result = index.search_candidates("OpenAI agent", top_k=3)

    assert search_result["provider"] == "opensearch"
    assert search_result["query"] == "OpenAI agent"
    assert search_result["items"][0]["candidate_id"] == "cand_001"
    assert client.post_requests[0]["url"] == (
        "http://localhost:9200/industry-news-candidates/_search"
    )
    assert client.post_requests[0]["timeout"] == 3.0
    assert client.post_requests[0]["json"] == {
        "size": 3,
        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": "OpenAI agent",
                            "fields": [
                                "title^3",
                                "raw_summary^2",
                                "content",
                                "decision_reason",
                            ],
                        }
                    }
                ]
            }
        },
    }


def test_opensearch_history_index_search_excludes_current_run_documents() -> None:
    from app.search.history_index import OpenSearchHistoryIndex

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self.payload

    class FakeClient:
        def __init__(self) -> None:
            self.post_requests: list[dict[str, object]] = []

        def post(self, url: str, **kwargs: object) -> FakeResponse:
            self.post_requests.append({"url": url, **kwargs})
            return FakeResponse({"hits": {"hits": []}})

    client = FakeClient()
    index = OpenSearchHistoryIndex(
        base_url="http://localhost:9200",
        index_name="industry-news-candidates",
        http_client=client,
        timeout_seconds=3.0,
    )

    search_result = index.search_candidates(
        "OpenAI agent",
        top_k=3,
        exclude_run_id="run_001",
    )

    assert search_result == {
        "provider": "opensearch",
        "query": "OpenAI agent",
        "items": [],
    }
    assert client.post_requests[0]["json"] == {
        "size": 3,
        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": "OpenAI agent",
                            "fields": [
                                "title^3",
                                "raw_summary^2",
                                "content",
                                "decision_reason",
                            ],
                        }
                    }
                ],
                "must_not": [
                    {"term": {"run_id": "run_001"}},
                ],
            }
        },
    }


def test_build_history_index_returns_noop_without_complete_opensearch_settings() -> None:
    from app.search.history_index import NoopHistoryIndex, build_history_index

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        history_index_provider="opensearch",
        opensearch_base_url=None,
    )

    assert isinstance(build_history_index(settings=settings), NoopHistoryIndex)


def test_task6_fetch_preserves_candidate_identity_when_urls_canonicalize_equal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.tools.browser_fetch_tool import BrowserFetchTool

    tool = BrowserFetchTool()
    monkeypatch.setattr(
        tool,
        "load_articles",
        lambda: [
            {
                "candidate_id": "cand_primary",
                "url": "https://example.com/articles/shared-story",
                "content": "Primary candidate body.",
            },
            {
                "candidate_id": "cand_duplicate",
                "url": "https://example.com/articles/shared-story?utm_source=dup",
                "content": "Duplicate candidate body.",
            },
        ],
    )

    response = tool(
        candidates=[
            {
                "candidate_id": "cand_primary",
                "url": "https://example.com/articles/shared-story",
                "raw_summary": "Primary summary",
            },
            {
                "candidate_id": "cand_duplicate",
                "url": "https://example.com/articles/shared-story?utm_source=dup",
                "raw_summary": "Duplicate summary",
            },
        ]
    )

    assert response.success is True
    assert response.data is not None
    fetched_candidates = response.data["candidates"]
    assert fetched_candidates[0]["content"] == "Primary candidate body."
    assert fetched_candidates[1]["content"] == "Duplicate candidate body."


def test_task6_decide_push_respects_history_url_and_cooldown_rules() -> None:
    from app.tools.registry import build_default_tool_registry

    topic = {
        **_build_task6_topic(),
        "cooldown_hours": 24,
    }
    registry = build_default_tool_registry(llm=MockLLM())
    gateway = LocalToolGateway()
    registry.register_into(gateway)

    response = gateway.call(
        "decide_push",
        run_id="run_task6_cooldown",
        topic=topic,
        now=datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
        push_history=[
            {
                "url": "https://example.com/articles/already-pushed",
                "title": "Historical title",
                "pushed_at": "2026-06-01T12:00:00Z",
            },
            {
                "url": "https://example.com/articles/older-url",
                "title": "Fresh Funding Round For Agent Startup",
                "pushed_at": "2026-06-09T02:00:00Z",
            },
        ],
        articles=[
            {
                "candidate_id": "cand_same_url",
                "extracted_id": "ext_same_url",
                "title": "Brand new title",
                "url": "https://example.com/articles/already-pushed?utm_source=again",
                "score": 0.91,
                "score_breakdown": "base llm=0.81; trusted source +0.10",
            },
            {
                "candidate_id": "cand_same_title",
                "extracted_id": "ext_same_title",
                "title": "Fresh funding round for agent startup",
                "url": "https://example.com/articles/new-url",
                "score": 0.93,
                "score_breakdown": "base llm=0.83; trusted source +0.10",
            },
            {
                "candidate_id": "cand_allowed",
                "extracted_id": "ext_allowed",
                "title": "OpenAI ships enterprise agent governance update",
                "url": "https://example.com/articles/openai-governance-update",
                "score": 0.88,
                "score_breakdown": "base llm=0.78; trusted source +0.10",
            },
        ],
    )

    assert response.success is True
    assert response.data is not None
    assert response.data["cooldown_hours"] == 24
    assert response.data["push_count"] == 1

    pushes = {push["candidate_id"]: push for push in response.data["pushes"]}
    assert pushes["cand_same_url"]["should_push"] is False
    assert "canonical_url already exists in push_history" in pushes["cand_same_url"][
        "decision_reason"
    ]
    assert pushes["cand_same_title"]["should_push"] is False
    assert "within cooldown 24h" in pushes["cand_same_title"]["decision_reason"]
    assert pushes["cand_allowed"]["should_push"] is True
