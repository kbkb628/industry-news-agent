from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings, get_settings

_ENGINE_REGISTRY: dict[str, Engine] = {}


class Base(DeclarativeBase):
    pass


def _resolve_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def build_engine(settings: Settings | None = None) -> Engine:
    resolved_settings = _resolve_settings(settings)
    return create_engine(
        resolved_settings.database_url,
        future=True,
        pool_pre_ping=True,
    )


def build_session_factory(
    engine: Engine,
) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def get_engine(settings: Settings | None = None) -> Engine:
    resolved_settings = _resolve_settings(settings)
    engine = _ENGINE_REGISTRY.get(resolved_settings.database_url)
    if engine is None:
        engine = build_engine(resolved_settings)
        _ENGINE_REGISTRY[resolved_settings.database_url] = engine
    return engine


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    return build_session_factory(get_engine(settings))


def reset_engine_registry(database_url: str | None = None) -> None:
    if database_url is not None:
        engine = _ENGINE_REGISTRY.pop(database_url, None)
        if engine is not None:
            engine.dispose()
        return

    engines = list(_ENGINE_REGISTRY.values())
    _ENGINE_REGISTRY.clear()
    for engine in engines:
        engine.dispose()
