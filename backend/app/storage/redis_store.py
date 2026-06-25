from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from redis import Redis

from app.core.config import Settings, get_settings


class RedisEphemeralStateStore:
    def __init__(
        self,
        redis_client: Redis,
        *,
        namespace: str = "industry_news_agent:coordination",
    ) -> None:
        self.redis_client = redis_client
        self.namespace = namespace
        self._fallback_values: dict[str, tuple[str, datetime]] = {}

    def _key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def _expires_at(self, ttl_seconds: int) -> datetime:
        return datetime.now(UTC) + timedelta(seconds=ttl_seconds)

    def _prune_fallback(self) -> None:
        now = datetime.now(UTC)
        expired_keys = [
            key for key, (_, expires_at) in self._fallback_values.items() if expires_at <= now
        ]
        for key in expired_keys:
            del self._fallback_values[key]

    def claim_value(
        self,
        *,
        key: str,
        value: str,
        ttl_seconds: int,
    ) -> bool:
        if not hasattr(self.redis_client, "set"):
            self._prune_fallback()
            namespaced_key = self._key(key)
            if namespaced_key in self._fallback_values:
                return False
            self._fallback_values[namespaced_key] = (value, self._expires_at(ttl_seconds))
            return True
        return bool(
            self.redis_client.set(
                self._key(key),
                value,
                ex=ttl_seconds,
                nx=True,
            )
        )

    def get_value(self, key: str) -> str | None:
        if not hasattr(self.redis_client, "get"):
            self._prune_fallback()
            payload = self._fallback_values.get(self._key(key))
            if payload is None:
                return None
            return payload[0]
        value = self.redis_client.get(self._key(key))
        if value is None:
            return None
        return str(value)

    def set_json(
        self,
        *,
        key: str,
        payload: dict[str, Any],
        ttl_seconds: int,
    ) -> dict[str, Any]:
        if not hasattr(self.redis_client, "set"):
            self._fallback_values[self._key(key)] = (
                json.dumps(payload),
                self._expires_at(ttl_seconds),
            )
            return dict(payload)
        self.redis_client.set(
            self._key(key),
            json.dumps(payload),
            ex=ttl_seconds,
        )
        return dict(payload)

    def get_json(self, key: str) -> dict[str, Any] | None:
        if not hasattr(self.redis_client, "get"):
            self._prune_fallback()
            raw = self._fallback_values.get(self._key(key))
            if raw is None:
                return None
            return dict(json.loads(raw[0]))
        raw = self.redis_client.get(self._key(key))
        if raw is None:
            return None
        return dict(json.loads(str(raw)))

    def delete(self, key: str) -> None:
        if not hasattr(self.redis_client, "delete"):
            self._fallback_values.pop(self._key(key), None)
            return
        self.redis_client.delete(self._key(key))


def build_redis_client(settings: Settings | None = None) -> Redis:
    resolved_settings = settings or get_settings()
    return Redis.from_url(
        resolved_settings.redis_url,
        decode_responses=True,
    )
