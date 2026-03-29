#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TENANT_ID="${TENANT_ID:-tenant-a}"

curl -sS -X POST "${BASE_URL}/documents" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: ${TENANT_ID}" \
  -d '{
    "id": "doc-1",
    "title": "Distributed Search Service",
    "body": "Tenant-aware full text search with caching and rate limiting.",
    "metadata": {
      "source": "sample"
    }
  }'

curl -sS "${BASE_URL}/documents/doc-1" \
  -H "X-Tenant-ID: ${TENANT_ID}"

curl -sS "${BASE_URL}/search?q=tenant%20search" \
  -H "X-Tenant-ID: ${TENANT_ID}"

curl -sS -X DELETE "${BASE_URL}/documents/doc-1" \
  -H "X-Tenant-ID: ${TENANT_ID}"

curl -sS "${BASE_URL}/health"
