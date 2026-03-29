# Distributed Document Search Service

Multi-tenant document search prototype built with `FastAPI`, `OpenSearch`, `Redis`, and `Docker Compose`.

This repository was built for the distributed search service assignment and is meant to be a production-shaped prototype rather than a toy demo. It focuses on tenant isolation, relevance-ranked full-text search, caching, rate limiting, dependency health, and a clean path toward asynchronous indexing and horizontal scale.

For a reviewer-friendly summary of the architecture, production-readiness analysis, testing approach, experience showcase, and AI usage note, start with [`docs/submission.md`](docs/submission.md).

## Architecture At A Glance

- `FastAPI` serves the REST API and generated OpenAPI docs
- `OpenSearch` is the primary full-text search engine
- `Redis` is used for caching and per-tenant rate limiting
- `Docker Compose` runs the local multi-service stack

## Quick Start

```bash
docker compose up --build -d
```

API docs:

- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

Health check:

- `http://localhost:8000/health`

## API Surface

- `POST /documents` indexes a document for a tenant
- `GET /documents/{id}` returns a document for the active tenant
- `DELETE /documents/{id}` removes a document for the active tenant
- `GET /search?q={query}` searches documents for the active tenant
- `GET /health` reports API and dependency status

Tenant context is passed through the `X-Tenant-ID` header. Search uses OpenSearch relevance ranking, fuzzy matching, and highlighting. Caching and rate limiting are tenant-aware.

## Development And Testing

```bash
python3 -m pip install -r requirements.txt
uvicorn app.main:app --reload
pytest -q
```

Live verification against the Docker stack:

```bash
docker compose up --build -d
python3 examples/live_api_checks.py
```

The live verification script exercises:

- health checks
- document create, fetch, search, and delete
- post-delete `404` behavior
- per-tenant rate limiting
- multi-tenant isolation

Manual sample requests:

```bash
bash examples/curl_requests.sh
```

Postman collection:

- [`examples/postman_collection.json`](examples/postman_collection.json)

## Key Files

- [`app/main.py`](app/main.py)
- [`app/api/routes.py`](app/api/routes.py)
- [`app/services/document_service.py`](app/services/document_service.py)
- [`app/clients/opensearch_store.py`](app/clients/opensearch_store.py)
- [`app/services/rate_limiter.py`](app/services/rate_limiter.py)
- [`examples/live_api_checks.py`](examples/live_api_checks.py)
- [`docs/submission.md`](docs/submission.md)

## Documentation

- Architecture, production-readiness analysis, experience showcase, and AI usage note: [`docs/submission.md`](docs/submission.md)
