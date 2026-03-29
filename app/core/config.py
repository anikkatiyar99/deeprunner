from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Distributed Document Search Service"
    app_version: str = "0.1.0"
    environment: str = "development"

    opensearch_url: str = "http://opensearch:9200"
    opensearch_index_prefix: str = "documents"
    opensearch_refresh: str = "wait_for"

    redis_url: str = "redis://redis:6379/0"
    cache_ttl_seconds: int = 30
    rate_limit_requests_per_minute: int = 120
    rate_limit_window_seconds: int = 60

    default_search_limit: int = 10
    max_search_limit: int = 50

    request_timeout_seconds: int = 3
    health_timeout_seconds: int = 2
    supported_tenant_header: str = "X-Tenant-ID"
    allowed_tenant_pattern: str = r"^[a-zA-Z0-9_-]{2,64}$"

    search_fields: list[str] = Field(default_factory=lambda: ["title^3", "content", "tags^2"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
