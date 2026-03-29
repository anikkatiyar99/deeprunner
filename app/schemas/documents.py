from datetime import datetime, timezone
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class DocumentCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "doc-123",
                "title": "Quarterly Revenue Report",
                "content": "Revenue increased by 12 percent in Q1 across enterprise tenants.",
                "tags": ["finance", "q1", "report"],
                "metadata": {"source": "upload", "department": "finance"},
            }
        }
    )

    id: str | None = Field(default=None, min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    content: str = Field(min_length=1, max_length=100_000, validation_alias=AliasChoices("content", "body"))
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, tags: list[str]) -> list[str]:
        normalized = []
        for tag in tags:
            candidate = tag.strip()
            if candidate:
                normalized.append(candidate)
        return normalized


class DocumentRecord(BaseModel):
    id: str
    tenant_id: str
    title: str
    content: str = Field(validation_alias=AliasChoices("content", "body"))
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentResponse(DocumentRecord):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "doc-123",
                "tenant_id": "tenant-a",
                "title": "Quarterly Revenue Report",
                "content": "Revenue increased by 12 percent in Q1 across enterprise tenants.",
                "tags": ["finance", "q1", "report"],
                "metadata": {"source": "upload", "department": "finance"},
                "created_at": "2026-03-29T00:00:00Z",
                "updated_at": "2026-03-29T00:00:00Z",
                "indexed": True,
            }
        }
    )

    indexed: bool = True


class SearchHit(BaseModel):
    id: str
    score: float | None = None
    title: str
    snippet: str = Field(default="", validation_alias=AliasChoices("snippet", "body", "content"))
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    highlights: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "revenue",
                "tenant_id": "tenant-a",
                "total": 1,
                "count": 1,
                "took_ms": 18,
                "cached": False,
                "results": [
                    {
                        "id": "doc-123",
                        "score": 12.47,
                        "title": "Quarterly Revenue Report",
                        "snippet": "Revenue increased by 12 percent in Q1 across enterprise tenants.",
                        "tags": ["finance", "q1", "report"],
                        "metadata": {"source": "upload", "department": "finance"},
                        "highlights": ["<em>Revenue</em> increased by 12 percent in Q1."],
                    }
                ],
            }
        }
    )

    query: str
    tenant_id: str
    total: int = Field(default=0)
    count: int = Field(default=0)
    took_ms: int = 0
    cached: bool = False
    results: list[SearchHit] = Field(default_factory=list)


class DeleteDocumentResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "doc-123",
                "tenant_id": "tenant-a",
                "deleted": True,
            }
        }
    )

    id: str
    tenant_id: str
    deleted: bool


class DependencyHealth(BaseModel):
    healthy: bool
    backend: str
    details: str


class HealthResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "service": "Distributed Document Search Service",
                "version": "0.1.0",
                "dependencies": {
                    "search": {
                        "healthy": True,
                        "backend": "opensearch",
                        "details": "OpenSearch reachable.",
                    },
                    "cache": {
                        "healthy": True,
                        "backend": "redis",
                        "details": "Redis reachable.",
                    },
                },
            }
        }
    )

    status: str
    service: str
    version: str
    dependencies: dict[str, DependencyHealth]
