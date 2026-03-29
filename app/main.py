from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.dependencies import get_document_service, get_rate_limiter
from app.api.routes import router
from app.core.config import get_settings
from app.services.errors import SearchBackendError


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Prototype distributed document search service with multi-tenant isolation, caching, and rate limiting.",
        docs_url="/docs",
        openapi_url="/openapi.json",
        openapi_tags=[
            {"name": "meta", "description": "Service metadata and API documentation links."},
            {"name": "documents", "description": "Document indexing, retrieval, and deletion operations."},
            {"name": "search", "description": "Tenant-scoped full-text search operations."},
            {"name": "health", "description": "Service and dependency health status."},
        ],
    )
    application.include_router(router)

    @application.exception_handler(SearchBackendError)
    async def handle_search_backend_error(_, exc: SearchBackendError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @application.get("/", tags=["meta"])
    def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "openapi": "/openapi.json",
        }

    return application


app = create_app()
