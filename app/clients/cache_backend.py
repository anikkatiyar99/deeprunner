import json
import logging
import time
from threading import Lock
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


_MAX_CACHE_ENTRIES = 10_000


class InMemoryTTLCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}
        self._lock = Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            record = self._store.get(key)
            if record is None:
                return None

            expires_at, payload = record
            if expires_at < time.time():
                self._store.pop(key, None)
                return None

            return payload

    def set(self, key: str, payload: str, ttl_seconds: int) -> None:
        expires_at = time.time() + ttl_seconds
        with self._lock:
            if len(self._store) >= _MAX_CACHE_ENTRIES and key not in self._store:
                # Evict one expired entry, or the oldest if none are expired
                now = time.time()
                victim = next(
                    (k for k, (exp, _) in self._store.items() if exp < now),
                    next(iter(self._store)),
                )
                self._store.pop(victim, None)
            self._store[key] = (expires_at, payload)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def delete_prefix(self, prefix: str) -> None:
        with self._lock:
            stale_keys = [key for key in self._store if key.startswith(prefix)]
            for key in stale_keys:
                self._store.pop(key, None)


class HybridCacheBackend:
    def __init__(self, redis_client: Redis | None, fallback: InMemoryTTLCache | None = None) -> None:
        self.redis_client = redis_client
        self.fallback = fallback or InMemoryTTLCache()

    def get_json(self, key: str) -> Any | None:
        payload = self._get_raw(key)
        if payload is None:
            return None
        return json.loads(payload)

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        payload = json.dumps(value)
        if not self._set_raw(key, payload, ttl_seconds):
            self.fallback.set(key, payload, ttl_seconds)

    def delete(self, key: str) -> None:
        try:
            if self.redis_client is not None:
                self.redis_client.delete(key)
        except RedisError as exc:
            logger.warning("Redis delete failed for key %r: %s", key, exc)
        self.fallback.delete(key)

    def delete_prefix(self, prefix: str) -> None:
        try:
            if self.redis_client is not None:
                keys = list(self.redis_client.scan_iter(match=f"{prefix}*"))
                if keys:
                    self.redis_client.delete(*keys)
        except RedisError as exc:
            logger.warning("Redis delete_prefix failed for prefix %r: %s", prefix, exc)
        self.fallback.delete_prefix(prefix)

    def health(self) -> tuple[bool, str, str]:
        if self.redis_client is None:
            return True, "memory", "Redis disabled; using in-memory fallback cache."

        try:
            self.redis_client.ping()
            return True, "redis", "Redis reachable."
        except RedisError as exc:
            return False, "memory-fallback", f"Redis unavailable, serving from in-memory fallback: {exc}"

    def _get_raw(self, key: str) -> str | None:
        try:
            if self.redis_client is not None:
                payload = self.redis_client.get(key)
                if payload is not None:
                    return payload
        except RedisError:
            pass
        return self.fallback.get(key)

    def _set_raw(self, key: str, payload: str, ttl_seconds: int) -> bool:
        try:
            if self.redis_client is not None:
                self.redis_client.setex(key, ttl_seconds, payload)
                return True
        except RedisError:
            return False
        return False
