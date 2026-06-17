import json
from datetime import UTC, datetime
from pathlib import Path
import time

import pytest
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
from app.scheduler.worker import (
    InMemoryRunQueue,
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
from app.storage.models import CandidateRecord, ExtractedItemRecord, Topic
from app.storage.repository import (
    CandidateRecordUpsertData,
    ExtractedItemRecordUpsertData,
    SqlAlchemyMonitorRunRepository,
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


def test_build_run_queue_falls_back_to_in_memory_when_redis_ping_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingRedis:
        def ping(self) -> bool:
            raise RedisError("redis unavailable")

    monkeypatch.setattr(
        "app.scheduler.worker.build_redis_client",
        lambda settings=None: FailingRedis(),
    )

    queue = build_run_queue()

    assert isinstance(queue, InMemoryRunQueue)


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
        "fetch_article_content",
        "extract_article",
        "deduplicate_items",
        "score_candidate",
        "decide_push",
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
