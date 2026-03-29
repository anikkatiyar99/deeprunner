from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.dependencies import (
    enforce_rate_limit,
    get_document_service,
    get_rate_limiter,
)
from app.api.service_adapter import DocumentServiceAdapter, HealthServiceAdapter
from app.core.config import get_settings
from app.core.tenancy import resolve_tenant_id
from app.schemas.documents import (
    DeleteDocumentResponse,
    DocumentCreate,
    DocumentResponse,
    HealthResponse,
    SearchResponse,
)

SETTINGS = get_settings()
router = APIRouter()

@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["health"],
    summary="Check service health",
    description="Returns overall service status plus dependency health for search and cache backends.",
)
def get_health(service: object = Depends(get_document_service)) -> HealthResponse:
    return HealthServiceAdapter(service).get_health()


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["documents"],
    summary="Index a document",
    description="Indexes a document for the resolved tenant and invalidates tenant-specific search cache entries.",
)
def create_document(
    payload: DocumentCreate,
    response: Response,
    tenant_id: str = Depends(resolve_tenant_id),
    service: object = Depends(get_document_service),
    rate_limiter: object = Depends(get_rate_limiter),
) -> DocumentResponse:
    enforce_rate_limit(tenant_id, response, rate_limiter)
    return DocumentServiceAdapter(service).create_document(tenant_id, payload)


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    tags=["documents"],
    summary="Get a document",
    description="Fetches a single tenant-scoped document by its ID.",
)
def get_document(
    document_id: str,
    response: Response,
    tenant_id: str = Depends(resolve_tenant_id),
    service: object = Depends(get_document_service),
    rate_limiter: object = Depends(get_rate_limiter),
) -> DocumentResponse:
    enforce_rate_limit(tenant_id, response, rate_limiter)
    record = DocumentServiceAdapter(service).get_document(tenant_id, document_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return record


@router.delete(
    "/documents/{document_id}",
    response_model=DeleteDocumentResponse,
    tags=["documents"],
    summary="Delete a document",
    description="Deletes a tenant-scoped document and invalidates related cache entries.",
)
def delete_document(
    document_id: str,
    response: Response,
    tenant_id: str = Depends(resolve_tenant_id),
    service: object = Depends(get_document_service),
    rate_limiter: object = Depends(get_rate_limiter),
) -> DeleteDocumentResponse:
    enforce_rate_limit(tenant_id, response, rate_limiter)
    deleted = DocumentServiceAdapter(service).delete_document(tenant_id, document_id)
    if not deleted.deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return deleted


@router.get(
    "/search",
    response_model=SearchResponse,
    tags=["search"],
    summary="Search documents",
    description="Runs a full-text query against the tenant's search index with relevance ranking, highlighting, and cache support.",
)
def search_documents(
    response: Response,
    q: str = Query(min_length=1, description="Full-text query string"),
    limit: int = Query(default=SETTINGS.default_search_limit, ge=1),
    tenant_id: str = Depends(resolve_tenant_id),
    service: object = Depends(get_document_service),
    rate_limiter: object = Depends(get_rate_limiter),
) -> SearchResponse:
    if limit > SETTINGS.max_search_limit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"limit cannot exceed {SETTINGS.max_search_limit}.",
        )
    enforce_rate_limit(tenant_id, response, rate_limiter)
    return DocumentServiceAdapter(service).search_documents(tenant_id, q, limit)
