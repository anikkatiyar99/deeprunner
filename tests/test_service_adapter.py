from app.api.service_adapter import DocumentServiceAdapter, HealthServiceAdapter
from app.schemas.documents import DocumentCreate


class StubDocumentService:
    def create_document(self, tenant_id: str, payload: object) -> dict[str, object]:
        content = payload.content if hasattr(payload, "content") else payload.get("content", "")
        return {
            "id": "doc-1",
            "tenant_id": tenant_id,
            "title": "Normalized",
            "content": content,
            "metadata": {},
            "indexed": True,
        }

    def get_document(self, tenant_id: str, document_id: str) -> dict[str, object]:
        return {
            "id": document_id,
            "tenant_id": tenant_id,
            "title": "Normalized",
            "content": "Stored body",
            "metadata": {},
        }

    def delete_document(self, tenant_id: str, document_id: str) -> dict[str, object]:
        return {"id": document_id, "deleted": True}

    def search_documents(self, tenant_id: str, query: str, limit: int) -> dict[str, object]:
        return {
            "tenant_id": tenant_id,
            "query": query,
            "count": 1,
            "total": 1,
            "results": [
                {
                    "id": "doc-1",
                    "title": "Normalized",
                    "content": "Stored body",
                    "score": 1.0,
                    "metadata": {},
                }
            ],
        }


class StubHealthService:
    def healthcheck(self) -> dict[str, object]:
        return {
            "status": "degraded",
            "dependencies": {
                "search": {"status": "down"},
                "cache": {"status": "ok"},
            },
        }


def test_document_service_adapter_normalizes_response_shapes() -> None:
    adapter = DocumentServiceAdapter(StubDocumentService())
    payload = DocumentCreate(id="doc-1", title="Normalized", content="Stored body")

    created = adapter.create_document("tenant-a", payload)
    fetched = adapter.get_document("tenant-a", "doc-1")
    deleted = adapter.delete_document("tenant-a", "doc-1")
    search = adapter.search_documents("tenant-a", "stored", 10)

    assert created.indexed is True
    assert created.tenant_id == "tenant-a"
    assert fetched is not None
    assert fetched.content == "Stored body"
    assert deleted.tenant_id == "tenant-a"
    assert deleted.deleted is True
    assert search.count == 1
    assert search.total == 1
    assert search.results[0].snippet == "Stored body"


def test_health_service_adapter_normalizes_health_shape() -> None:
    health = HealthServiceAdapter(StubHealthService()).get_health()

    assert health.status == "degraded"
    assert health.dependencies["search"].healthy is False
    assert health.dependencies["cache"].healthy is True
