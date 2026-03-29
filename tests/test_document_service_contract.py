import importlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from app.services.rate_limiter import HybridRateLimiter

_UNLIMITED_RATE_LIMITER = HybridRateLimiter(redis_client=None, limit=10_000, window_seconds=60)


APP_MODULE_CANDIDATES = (
    "app.main",
    "main",
)


def _load_app() -> Any:
    last_error: Optional[Exception] = None
    for module_name in APP_MODULE_CANDIDATES:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - intentional contract helper
            last_error = exc
            continue

        if hasattr(module, "create_app"):
            return module.create_app()
        if hasattr(module, "app"):
            return module.app

    raise RuntimeError(
        "Could not import a FastAPI app. Expected either app.main:create_app() "
        "or app.main:app (or main:create_app/app)."
    ) from last_error


def _load_app_module() -> Any:
    last_error: Optional[Exception] = None
    for module_name in APP_MODULE_CANDIDATES:
        try:
            return importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - intentional contract helper
            last_error = exc
    raise RuntimeError("Could not import the app module for dependency overrides.") from last_error


@dataclass
class FakeDocument:
    id: str
    tenant_id: str
    title: str
    content: str
    metadata: Dict[str, Any]


class FakeDocumentService:
    def __init__(self, search_ok: bool = True, cache_ok: bool = True) -> None:
        self.documents: Dict[str, FakeDocument] = {}
        self.deleted_ids: List[str] = []
        self.search_ok = search_ok
        self.cache_ok = cache_ok

    def _seed(self, tenant_id: str, payload: Dict[str, Any]) -> FakeDocument:
        """Helper for pre-seeding documents directly in tests."""
        doc = FakeDocument(
            id=payload["id"],
            tenant_id=tenant_id,
            title=payload["title"],
            content=payload.get("content", payload.get("body", "")),
            metadata=payload.get("metadata", {}),
        )
        self.documents[doc.id] = doc
        return doc

    def create_document(self, tenant_id: str, payload: Any) -> Dict[str, Any]:
        content = payload.content if hasattr(payload, "content") else payload.get("content", "")
        title = payload.title if hasattr(payload, "title") else payload.get("title", "")
        doc_id = (payload.id if hasattr(payload, "id") else payload.get("id")) or str(len(self.documents) + 1)
        metadata = payload.metadata if hasattr(payload, "metadata") else payload.get("metadata", {})
        doc = FakeDocument(id=doc_id, tenant_id=tenant_id, title=title, content=content, metadata=metadata)
        self.documents[doc.id] = doc
        return {"id": doc.id, "tenant_id": doc.tenant_id, "title": doc.title, "content": doc.content, "metadata": doc.metadata, "indexed": True}

    def get_document(self, tenant_id: str, document_id: str) -> Optional[Dict[str, Any]]:
        doc = self.documents.get(document_id)
        if doc is None or doc.tenant_id != tenant_id:
            return None
        return {"id": doc.id, "tenant_id": doc.tenant_id, "title": doc.title, "content": doc.content, "metadata": doc.metadata}

    def delete_document(self, tenant_id: str, document_id: str) -> Dict[str, Any]:
        doc = self.documents.get(document_id)
        if doc is None or doc.tenant_id != tenant_id:
            return {"deleted": False, "id": document_id}
        self.deleted_ids.append(document_id)
        del self.documents[document_id]
        return {"deleted": True, "id": document_id}

    def search_documents(self, tenant_id: str, query: str, limit: int = 10) -> Dict[str, Any]:
        hits = [
            {"id": doc.id, "tenant_id": doc.tenant_id, "title": doc.title, "content": doc.content, "score": 1.0}
            for doc in self.documents.values()
            if doc.tenant_id == tenant_id and query.lower() in f"{doc.title} {doc.content}".lower()
        ][:limit]
        return {"tenant_id": tenant_id, "query": query, "results": hits, "count": len(hits), "total": len(hits)}

    def healthcheck(self) -> Dict[str, Any]:
        return {
            "status": "ok" if self.search_ok and self.cache_ok else "degraded",
            "dependencies": {
                "search": {"status": "ok" if self.search_ok else "down"},
                "cache": {"status": "ok" if self.cache_ok else "down"},
            },
        }




@pytest.fixture()
def client() -> TestClient:
    app = _load_app()
    return TestClient(app)


@pytest.fixture()
def tenant_headers() -> Dict[str, str]:
    return {"X-Tenant-ID": "tenant-a"}


def _configure_overrides(app: Any, document_service: FakeDocumentService) -> None:
    overrides = getattr(app, "dependency_overrides", None)
    if overrides is None:
        pytest.skip("The app does not expose FastAPI dependency_overrides.")

    app_module = _load_app_module()

    overrides.clear()
    if hasattr(app_module, "get_document_service"):
        overrides[app_module.get_document_service] = lambda: document_service
    if hasattr(app_module, "get_rate_limiter"):
        overrides[app_module.get_rate_limiter] = lambda: _UNLIMITED_RATE_LIMITER


def test_post_document_indexes_and_returns_document(client: TestClient, tenant_headers: Dict[str, str]) -> None:
    app = client.app
    document_service = FakeDocumentService()
    _configure_overrides(app, document_service)

    response = client.post(
        "/documents",
        headers=tenant_headers,
        json={
            "id": "doc-1",
            "title": "Distributed Search",
            "content": "Fast relevance ranking across tenants",
            "metadata": {"source": "upload"},
        },
    )

    assert response.status_code in (200, 201)
    payload = response.json()
    assert payload["id"] == "doc-1"
    assert payload["tenant_id"] == "tenant-a"
    assert payload["indexed"] is True


def test_get_document_returns_tenant_scoped_document(client: TestClient, tenant_headers: Dict[str, str]) -> None:
    app = client.app
    document_service = FakeDocumentService()
    _configure_overrides(app, document_service)
    document_service._seed(
        "tenant-a",
        {"id": "doc-2", "title": "Tenant Isolation", "content": "Separate data paths", "metadata": {}},
    )

    response = client.get("/documents/doc-2", headers=tenant_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "doc-2"
    assert payload["tenant_id"] == "tenant-a"


def test_delete_document_removes_tenant_document(client: TestClient, tenant_headers: Dict[str, str]) -> None:
    app = client.app
    document_service = FakeDocumentService()
    _configure_overrides(app, document_service)
    document_service._seed(
        "tenant-a",
        {"id": "doc-3", "title": "Remove Me", "content": "delete flow", "metadata": {}},
    )

    response = client.delete("/documents/doc-3", headers=tenant_headers)

    assert response.status_code in (200, 202, 204)
    if response.status_code != 204:
        assert response.json()["deleted"] is True


def test_search_requires_tenant_and_returns_ranked_hits(client: TestClient, tenant_headers: Dict[str, str]) -> None:
    app = client.app
    document_service = FakeDocumentService()
    _configure_overrides(app, document_service)
    document_service._seed(
        "tenant-a",
        {"id": "doc-4", "title": "OpenSearch", "content": "full text search", "metadata": {}},
    )
    document_service._seed(
        "tenant-b",
        {"id": "doc-5", "title": "Other tenant", "content": "full text search", "metadata": {}},
    )

    response = client.get("/search", params={"q": "search"}, headers=tenant_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == "tenant-a"
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "doc-4"


def test_search_rejects_missing_query(client: TestClient, tenant_headers: Dict[str, str]) -> None:
    app = client.app
    document_service = FakeDocumentService()
    _configure_overrides(app, document_service)

    response = client.get("/search", headers=tenant_headers)

    assert response.status_code in (400, 422)


def test_health_reports_dependency_status(client: TestClient) -> None:
    app = client.app
    document_service = FakeDocumentService(search_ok=True, cache_ok=False)
    _configure_overrides(app, document_service)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert "dependencies" in payload
    assert "search" in payload["dependencies"]
    assert "cache" in payload["dependencies"]


def test_rate_limit_is_enforced_per_tenant(client: TestClient, tenant_headers: Dict[str, str]) -> None:
    app = client.app
    document_service = FakeDocumentService()
    _configure_overrides(app, document_service)

    # Use a tight in-memory limiter so we can deterministically trigger 429
    tight_limiter = HybridRateLimiter(redis_client=None, limit=3, window_seconds=60)
    app_module = _load_app_module()
    if hasattr(app_module, "get_rate_limiter"):
        app.dependency_overrides[app_module.get_rate_limiter] = lambda: tight_limiter

    statuses = [
        client.get("/search", params={"q": "anything"}, headers=tenant_headers).status_code
        for _ in range(5)
    ]

    assert statuses[:3] == [200, 200, 200], "First 3 requests should succeed"
    assert all(s == 429 for s in statuses[3:]), "Requests beyond limit=3 should be 429"

    # Verify Retry-After header is present on the 429
    over_limit = client.get("/search", params={"q": "anything"}, headers=tenant_headers)
    assert over_limit.status_code == 429
    assert over_limit.headers.get("Retry-After") is not None


def test_other_tenant_cannot_access_document(client: TestClient) -> None:
    app = client.app
    document_service = FakeDocumentService()
    _configure_overrides(app, document_service)
    document_service._seed(
        "tenant-a",
        {"id": "doc-6", "title": "Private", "content": "tenant scoped", "metadata": {}},
    )

    response = client.get("/documents/doc-6", headers={"X-Tenant-ID": "tenant-b"})

    assert response.status_code in (403, 404)
