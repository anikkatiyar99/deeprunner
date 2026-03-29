# Distributed Document Search Service

This repository contains a working prototype of a multi-tenant document search service built with `FastAPI`, `OpenSearch`, `Redis`, and `Docker Compose`. The implementation is intentionally small enough to run locally, but the design choices are aimed at a production-shaped system: tenant isolation, relevance-ranked search, caching, rate limiting, health visibility, and a clear path to horizontal scale.

## 1. Architecture Design

### High-Level System

```text
Clients
  |
  v
API / Ingress
  |
  v
FastAPI Search Service
  |-- Tenant Resolver
  |-- Rate Limiter (Redis)
  |-- Cache (Redis)
  |-- Document/Search Service
  |
  +--> OpenSearch
  +--> Message Queue (production target)
  +--> Metadata Store (production target)
```

### Data Flow

```text
Indexing
POST /documents
  -> validate request + tenant
  -> write to tenant-specific OpenSearch index
  -> invalidate document/query cache

Search
GET /search?q=...
  -> validate tenant
  -> rate-limit check
  -> cache lookup
  -> OpenSearch query + ranking
  -> cache hot result
  -> return response
```

### Storage And API Strategy

- `OpenSearch` is the primary search store because it gives BM25 relevance, analyzers, fuzzy matching, highlighting, and shard-based scale.
- `Redis` is used for query/document caching and per-tenant rate limiting.
- In the prototype, canonical document content lives in OpenSearch to keep the stack lean. In production, PostgreSQL would be added for metadata, audit history, retention state, and indexing status.
- The prototype uses one index per tenant for straightforward logical isolation. In production, a mixed model would make sense: shared indices for smaller tenants and dedicated indices or clusters for high-volume tenants.

Key endpoints:

- `POST /documents`
- `GET /documents/{id}`
- `DELETE /documents/{id}`
- `GET /search?q={query}`
- `GET /health`

Example index payload:

```json
{
  "id": "doc-123",
  "title": "Quarterly Report",
  "content": "Revenue increased by 12 percent...",
  "tags": ["finance", "q1"]
}
```

Example search response:

```json
{
  "tenant_id": "tenant-a",
  "query": "revenue",
  "results": [
    { "id": "doc-123", "title": "Quarterly Report", "score": 12.47 }
  ]
}
```

### Consistency, Caching, And Queueing

- The prototype uses synchronous indexing with `refresh=wait_for`, so documents are searchable immediately after a successful write.
- That is a deliberate prototype trade-off. In production, writes should move to a queue-backed indexing pipeline with eventual consistency in exchange for higher throughput and better fault isolation.
- In the current prototype, Redis is used as an exact-match cache. Document reads are cached by `tenant + document_id`, and search results are cached by `tenant + query + limit`, with TTL-based expiry. Deletes invalidate cache entries immediately.
- Semantic caching is not implemented in the prototype. A production implementation would add a second cache tier for semantically similar queries: generate an embedding for the incoming query, search prior cached query embeddings within the same tenant, and reuse a cached response only when the similarity score clears a threshold and the cache entry was created against the current index or document-set version.
- That semantic layer would work best around expensive retrieval or reranking stages rather than as a blanket replacement for normal exact-query caching. Exact-match caching would remain the first layer because it is cheaper, simpler, and deterministic.
- The production design would add an asynchronous queue such as SQS, Kafka, or Redis Streams for indexing and deletion, along with retries, dead-letter handling, and replay tooling.

### Multi-Tenancy

- Every request carries tenant context through the `X-Tenant-ID` header.
- Tenant scope is enforced in request handling, cache namespacing, rate limiting, and OpenSearch index selection.
- This prototype demonstrates logical isolation; production isolation can be strengthened by moving large or sensitive tenants to dedicated indices or clusters.

## 2. Prototype Validation

The prototype was validated in two ways:

- `pytest -q` for API contract and adapter-level tests
- `docker compose up --build -d` plus `python3 examples/live_api_checks.py` for end-to-end verification on the real stack

The live checks cover:

- `GET /health`
- document create, fetch, search, and delete
- post-delete `404` behavior
- per-tenant rate limiting, including `429` responses
- tenant isolation for both search and point reads

Most recent local run results:

- smoke flow passed end to end
- search returned a live hit with highlighting
- rate limiting triggered on request `121`, matching the configured `120 requests/minute`
- cross-tenant reads returned `404`, confirming isolation on the prototype path

## 3. Production Readiness Analysis

- Scalability: scale the API horizontally behind a load balancer, bulk index asynchronously, tune shard layouts by tenant size and traffic, and split hot tenants onto dedicated search capacity.
- Resilience: add circuit breakers around Redis and OpenSearch, bounded retries with jitter, idempotent indexing, dead-letter queues, and replay tooling for failed events.
- Security: move tenant identity into trusted auth claims, enforce role-based authorization, use TLS in transit, encrypt data at rest, sanitize query input, and audit sensitive operations.
- Observability: emit structured logs with tenant and request IDs, collect p95/p99 latency, cache hit rate, OpenSearch error rate, queue lag, and add distributed tracing across API, cache, and search dependencies.
- Performance: tune analyzers, mappings, refresh intervals, and bulk sizes; keep pagination bounded; avoid expensive dynamic fields; use exact-match caching for repeated queries; and add semantic caching for high-cost retrieval or reranking paths where near-duplicate queries are common.
- Operations: deploy with blue-green or rolling updates, health-gated traffic shifting, snapshot-based backup and restore, and zero-downtime index migration playbooks.
- SLA: to target `99.95%` availability, run across multiple zones, keep redundant API and search nodes, isolate noisy tenants, and define SLOs for search latency, write acceptance, and recovery time.

## 4. Enterprise Experience Showcase

### Similar Distributed System

At Data Society, state-level multi-region infrastructure was architected for a community platform serving 500K+ educators. Each state had its own deployment boundary, with region-specific instances and district-level data isolation enforced through PostgreSQL RLS. That work maps directly to this assignment because the same concerns showed up there too: tenant isolation, blast-radius control, repeatable deployments, and shared-versus-dedicated infrastructure trade-offs.

### Performance Optimization

A hybrid search system was built using `pgvector`, BM25 retrieval, k-NN embeddings, Cross-Encoder reranking, and semantic caching in Redis. It reduced query latency by 60% and lowered LLM token costs by 40% for RAG-driven search. The main lesson was to separate recall from ranking and reserve expensive work for a narrow candidate set.

### Architectural Decision

One important decision at Data Society was how much physical isolation to give tenants. A fully dedicated stack per district would have been strongest for isolation but too expensive to operate, while a fully shared environment would have reduced cost at the expense of clean boundaries. We chose independent deployments per state, region-specific instances where needed, and PostgreSQL RLS inside each environment, which gave us a practical balance of isolation, cost, and operational complexity.

## 5. How AI Was Used

The scope, spec, architecture, and trade-offs for this submission were defined directly by me. That included deciding what the prototype needed to do, what could be simplified, and what had to be validated end to end.

AI tools were used to speed up implementation and documentation. It helped with boilerplate, iteration speed, and polish, but the architecture decisions, final direction, and review of the result remained driven by me.
