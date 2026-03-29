import time
from dataclasses import dataclass
from threading import Lock

from redis import Redis
from redis.exceptions import RedisError


@dataclass(slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int

    def headers(self) -> dict[str, str]:
        return {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(self.reset_seconds),
        }


_MAX_RATE_LIMITER_BUCKETS = 50_000


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._store: dict[str, tuple[int, int]] = {}
        self._lock = Lock()

    def check(self, tenant_id: str, limit: int, window_seconds: int) -> RateLimitResult:
        now = int(time.time())
        bucket = now // window_seconds
        key = f"{tenant_id}:{bucket}"

        with self._lock:
            current_bucket, current_count = self._store.get(key, (bucket, 0))
            if current_bucket != bucket:
                current_count = 0
            current_count += 1
            if len(self._store) >= _MAX_RATE_LIMITER_BUCKETS and key not in self._store:
                # Evict oldest bucket key (stale windows naturally sort first)
                self._store.pop(next(iter(self._store)), None)
            self._store[key] = (bucket, current_count)

        remaining = max(limit - current_count, 0)
        reset_seconds = window_seconds - (now % window_seconds)
        return RateLimitResult(
            allowed=current_count <= limit,
            limit=limit,
            remaining=remaining,
            reset_seconds=reset_seconds,
        )


class HybridRateLimiter:
    def __init__(self, redis_client: Redis | None, limit: int, window_seconds: int) -> None:
        self.redis_client = redis_client
        self.limit = limit
        self.window_seconds = window_seconds
        self.fallback = InMemoryRateLimiter()

    def check(self, tenant_id: str) -> RateLimitResult:
        if self.redis_client is None:
            return self.fallback.check(tenant_id, self.limit, self.window_seconds)

        now = int(time.time())
        bucket = now // self.window_seconds
        key = f"rate-limit:{tenant_id}:{bucket}"

        try:
            current_count = int(self.redis_client.incr(key))
            if current_count == 1:
                self.redis_client.expire(key, self.window_seconds)
        except RedisError:
            return self.fallback.check(tenant_id, self.limit, self.window_seconds)

        remaining = max(self.limit - current_count, 0)
        reset_seconds = self.window_seconds - (now % self.window_seconds)
        return RateLimitResult(
            allowed=current_count <= self.limit,
            limit=self.limit,
            remaining=remaining,
            reset_seconds=reset_seconds,
        )
