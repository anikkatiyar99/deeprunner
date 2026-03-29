from hashlib import sha256

from app.clients.cache_backend import HybridCacheBackend
from app.clients.opensearch_store import OpenSearchDocumentStore
from app.core.config import Settings
from app.schemas.documents import (
    DeleteDocumentResponse,
    DependencyHealth,
    DocumentCreate,
    DocumentResponse,
    HealthResponse,
    SearchResponse,
)


class DocumentService:
    def __init__(
        self,
        settings: Settings,
        store: OpenSearchDocumentStore,
        cache: HybridCacheBackend,
    ) -> None:
        self.settings = settings
        self.store = store
        self.cache = cache

    def create_document(self, tenant_id: str, payload: DocumentCreate) -> DocumentResponse:
        record = self.store.index_document(tenant_id, payload)
        response = self._to_document_response(record)
        self.cache.set_json(
            self._document_cache_key(tenant_id, response.id),
            response.model_dump(mode="json"),
            self.settings.cache_ttl_seconds,
        )
        self.cache.delete_prefix(self._search_cache_prefix(tenant_id))
        return response

    def get_document(self, tenant_id: str, document_id: str) -> DocumentResponse | None:
        cache_key = self._document_cache_key(tenant_id, document_id)
        cached = self.cache.get_json(cache_key)
        if cached is not None:
            return DocumentResponse.model_validate(cached)

        record = self.store.get_document(tenant_id, document_id)
        if record is None:
            return None

        response = self._to_document_response(record)
        self.cache.set_json(cache_key, response.model_dump(mode="json"), self.settings.cache_ttl_seconds)
        return response

    def delete_document(self, tenant_id: str, document_id: str) -> DeleteDocumentResponse:
        deleted = self.store.delete_document(tenant_id, document_id)
        self.cache.delete(self._document_cache_key(tenant_id, document_id))
        self.cache.delete_prefix(self._search_cache_prefix(tenant_id))
        return DeleteDocumentResponse(id=document_id, tenant_id=tenant_id, deleted=deleted)

    def search_documents(self, tenant_id: str, query: str, limit: int) -> SearchResponse:
        cache_key = self._search_cache_key(tenant_id, query, limit)
        cached = self.cache.get_json(cache_key)
        if cached is not None:
            response = SearchResponse.model_validate(cached)
            response.count = self._coerce_count(response)
            response.cached = True
            return response

        response = self.store.search_documents(tenant_id, query, limit)
        response.count = self._coerce_count(response)
        self.cache.set_json(cache_key, response.model_dump(mode="json"), self.settings.cache_ttl_seconds)
        return response

    def healthcheck(self) -> HealthResponse:
        opensearch_healthy, opensearch_backend, opensearch_details = self.store.health()
        cache_healthy, cache_backend, cache_details = self.cache.health()
        status = "ok" if opensearch_healthy and cache_healthy else "degraded"
        return HealthResponse(
            status=status,
            service=self.settings.app_name,
            version=self.settings.app_version,
            dependencies={
                "search": DependencyHealth(
                    healthy=opensearch_healthy,
                    backend=opensearch_backend,
                    details=opensearch_details,
                ),
                "cache": DependencyHealth(
                    healthy=cache_healthy,
                    backend=cache_backend,
                    details=cache_details,
                ),
            },
        )

    def _document_cache_key(self, tenant_id: str, document_id: str) -> str:
        return f"document:{tenant_id}:{document_id}"

    def _search_cache_prefix(self, tenant_id: str) -> str:
        return f"search:{tenant_id}:"

    def _search_cache_key(self, tenant_id: str, query: str, limit: int) -> str:
        digest = sha256(f"{tenant_id}:{query}:{limit}".encode("utf-8")).hexdigest()
        return f"{self._search_cache_prefix(tenant_id)}{digest}"

    @staticmethod
    def _coerce_count(response: SearchResponse) -> int:
        if response.count != 0:
            return response.count
        return len(response.results) if response.results else response.total

    @staticmethod
    def _to_document_response(record: DocumentResponse | object) -> DocumentResponse:
        if isinstance(record, DocumentResponse):
            return record
        if hasattr(record, "model_dump"):
            return DocumentResponse.model_validate(record.model_dump(mode="json"))
        return DocumentResponse.model_validate(record)
