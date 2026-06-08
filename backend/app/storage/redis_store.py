from redis import Redis

from app.core.config import Settings, get_settings


def build_redis_client(settings: Settings | None = None) -> Redis:
    resolved_settings = settings or get_settings()
    return Redis.from_url(
        resolved_settings.redis_url,
        decode_responses=True,
    )
