import json
from pathlib import Path

import pytest

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
from app.tools.responses import ToolResponse

from app.core.config import Settings, get_settings
from app.storage.database import (
    build_engine,
    build_session_factory,
    get_engine,
    get_session_factory,
    reset_engine_registry,
)
from app.storage.models import Topic
from app.storage.redis_store import build_redis_client


def test_settings_accept_explicit_connection_values() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
    )

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.redis_url.startswith("redis://")
    assert settings.default_push_threshold == 0.72


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


def test_build_redis_client_uses_configured_url_without_connecting() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/2",
    )

    client = build_redis_client(settings)

    assert client.connection_pool.connection_kwargs["decode_responses"] is True
    assert client.connection_pool.connection_kwargs["db"] == 2


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
