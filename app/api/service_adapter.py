from typing import Any

from app.core.config import get_settings
from app.schemas.documents import (
    DeleteDocumentResponse,
    DocumentCreate,
    DocumentResponse,
    HealthResponse,
    SearchResponse,
)


class DocumentServiceAdapter:
    """Thin adapter layer between route handlers and the document service."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def create_document(self, tenant_id: str, payload: DocumentCreate) -> DocumentResponse:
        result = self._service.create_document(tenant_id, payload)
        if isinstance(result, dict):
            result.setdefault("tenant_id", tenant_id)
            result.setdefault("indexed", True)
        return DocumentResponse.model_validate(result)

    def get_document(self, tenant_id: str, document_id: str) -> DocumentResponse | None:
        result = self._service.get_document(tenant_id, document_id)
        if result is None:
            return None
        return DocumentResponse.model_validate(result)

    def delete_document(self, tenant_id: str, document_id: str) -> DeleteDocumentResponse:
        result = self._service.delete_document(tenant_id, document_id)
        if isinstance(result, dict):
            result.setdefault("id", document_id)
            result.setdefault("tenant_id", tenant_id)
            result.setdefault("deleted", False)
        return DeleteDocumentResponse.model_validate(result)

    def search_documents(self, tenant_id: str, query: str, limit: int) -> SearchResponse:
        result = self._service.search_documents(tenant_id, query, limit)
        response = SearchResponse.model_validate(result)
        response.count = _coerce_count(response)
        if response.total == 0:
            response.total = response.count
        return response


class HealthServiceAdapter:
    """Normalizes health payloads from the document service."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def get_health(self) -> HealthResponse:
        payload = self._service.healthcheck()

        if isinstance(payload, HealthResponse):
            return payload

        dependencies = payload.get("dependencies", {})
        if "search" in dependencies and "cache" in dependencies and "opensearch" not in dependencies:
            settings = get_settings()
            payload = {
                "status": payload.get("status", "degraded"),
                "service": settings.app_name,
                "version": settings.app_version,
                "dependencies": {
                    "search": {
                        "healthy": dependencies["search"].get("status") == "ok",
                        "backend": "search",
                        "details": dependencies["search"].get("status", "unknown"),
                    },
                    "cache": {
                        "healthy": dependencies["cache"].get("status") == "ok",
                        "backend": "cache",
                        "details": dependencies["cache"].get("status", "unknown"),
                    },
                },
            }

        return HealthResponse.model_validate(payload)


def _coerce_count(response: SearchResponse) -> int:
    if response.count != 0:
        return response.count
    return len(response.results) if response.results else response.total
