from functools import lru_cache

from fastapi import HTTPException, Response, status
from redis import Redis

from app.clients.cache_backend import HybridCacheBackend
from app.clients.opensearch_store import OpenSearchDocumentStore
from app.core.config import Settings, get_settings
from app.services.document_service import DocumentService
from app.services.rate_limiter import HybridRateLimiter


@lru_cache
def get_redis_client() -> Redis | None:
    settings = get_settings()
    if not settings.redis_url:
        return None
    return Redis.from_url(settings.redis_url, decode_responses=True)


@lru_cache
def get_document_store() -> OpenSearchDocumentStore:
    return OpenSearchDocumentStore(get_settings())


@lru_cache
def get_cache_backend() -> HybridCacheBackend:
    return HybridCacheBackend(get_redis_client())


@lru_cache
def get_rate_limiter() -> HybridRateLimiter:
    settings = get_settings()
    return HybridRateLimiter(
        redis_client=get_redis_client(),
        limit=settings.rate_limit_requests_per_minute,
        window_seconds=settings.rate_limit_window_seconds,
    )


@lru_cache
def get_document_service() -> DocumentService:
    settings: Settings = get_settings()
    return DocumentService(
        settings=settings,
        store=get_document_store(),
        cache=get_cache_backend(),
    )



def enforce_rate_limit(tenant_id: str, response: Response, rate_limiter: HybridRateLimiter) -> None:
    result = rate_limiter.check(tenant_id)
    for key, value in result.headers().items():
        response.headers[key] = value

    if not result.allowed:
        response.headers["Retry-After"] = str(result.reset_seconds)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Tenant rate limit exceeded.",
            headers={**result.headers(), "Retry-After": str(result.reset_seconds)},
        )
