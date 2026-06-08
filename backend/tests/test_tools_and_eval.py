from pathlib import Path

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
