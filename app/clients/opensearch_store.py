from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError, OpenSearchException

from app.core.config import Settings
from app.schemas.documents import DocumentCreate, DocumentRecord, SearchHit, SearchResponse
from app.services.errors import SearchBackendError


class OpenSearchDocumentStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = OpenSearch(
            hosts=[settings.opensearch_url],
            timeout=settings.request_timeout_seconds,
            retry_on_timeout=True,
            max_retries=2,
        )

    def index_document(self, tenant_id: str, payload: DocumentCreate) -> DocumentRecord:
        try:
            index_name = self._build_index_name(tenant_id)
            self._ensure_index(index_name)

            now = datetime.now(timezone.utc)
            document_id = payload.id or str(uuid4())
            record = DocumentRecord(
                id=document_id,
                tenant_id=tenant_id,
                title=payload.title,
                content=payload.content,
                tags=payload.tags,
                metadata=payload.metadata,
                created_at=now,
                updated_at=now,
            )

            self.client.index(
                index=index_name,
                id=document_id,
                body=record.model_dump(mode="json"),
                refresh=self.settings.opensearch_refresh,
            )
            return record
        except OpenSearchException as exc:
            raise SearchBackendError("Failed to index the document in OpenSearch.") from exc

    def get_document(self, tenant_id: str, document_id: str) -> DocumentRecord | None:
        index_name = self._build_index_name(tenant_id)
        try:
            response = self.client.get(index=index_name, id=document_id)
        except NotFoundError:
            return None
        except OpenSearchException as exc:
            raise SearchBackendError("Failed to retrieve the document from OpenSearch.") from exc
        return self._record_from_source(document_id, response["_source"])

    def delete_document(self, tenant_id: str, document_id: str) -> bool:
        index_name = self._build_index_name(tenant_id)
        try:
            response = self.client.delete(
                index=index_name,
                id=document_id,
                refresh=self.settings.opensearch_refresh,
            )
        except NotFoundError:
            return False
        except OpenSearchException as exc:
            raise SearchBackendError("Failed to delete the document from OpenSearch.") from exc
        return response.get("result") == "deleted"

    def search_documents(self, tenant_id: str, query: str, limit: int) -> SearchResponse:
        index_name = self._build_index_name(tenant_id)
        try:
            if not self.client.indices.exists(index=index_name):
                return SearchResponse(query=query, tenant_id=tenant_id, total=0, took_ms=0, results=[])

            response = self.client.search(index=index_name, body=self._build_search_body(query, limit))
        except OpenSearchException as exc:
            raise SearchBackendError("Failed to query OpenSearch.") from exc

        total_obj = response["hits"]["total"]
        total = total_obj["value"] if isinstance(total_obj, dict) else int(total_obj)
        results = [self._build_search_hit(hit) for hit in response["hits"]["hits"]]
        return SearchResponse(
            query=query,
            tenant_id=tenant_id,
            total=total,
            count=len(results),
            took_ms=response.get("took", 0),
            results=results,
        )

    def health(self) -> tuple[bool, str, str]:
        try:
            if not self.client.ping():
                return False, "opensearch", "OpenSearch ping failed."
            return True, "opensearch", "OpenSearch reachable."
        except Exception as exc:
            return False, "opensearch", f"OpenSearch unavailable: {exc}"

    def _ensure_index(self, index_name: str) -> None:
        try:
            if self.client.indices.exists(index=index_name):
                return

            body: dict[str, Any] = {
                "settings": {
                    "index": {
                        "number_of_shards": 1,
                        "number_of_replicas": 0,
                    }
                },
                "mappings": {
                    "properties": {
                        "tenant_id": {"type": "keyword"},
                        "title": {"type": "text"},
                        "content": {"type": "text"},
                        "tags": {"type": "keyword"},
                        "metadata": {"type": "object", "enabled": False},
                        "created_at": {"type": "date"},
                        "updated_at": {"type": "date"},
                    }
                },
            }
            self.client.indices.create(index=index_name, body=body)
        except OpenSearchException as exc:
            raise SearchBackendError("Failed to prepare the tenant index in OpenSearch.") from exc

    def _build_search_body(self, query: str, limit: int) -> dict[str, Any]:
        return {
            "size": limit,
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": self.settings.search_fields,
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            },
            "highlight": {
                "pre_tags": ["<em>"],
                "post_tags": ["</em>"],
                "fields": {
                    "title": {},
                    "content": {"fragment_size": 180, "number_of_fragments": 1},
                },
            },
        }

    def _build_search_hit(self, hit: dict[str, Any]) -> SearchHit:
        source = hit["_source"]
        highlight = hit.get("highlight", {})
        title_highlights = highlight.get("title", [])
        content_highlights = highlight.get("content", [])
        snippet = content_highlights[0] if content_highlights else source.get("content", "")[:180].strip()
        title = title_highlights[0] if title_highlights else source.get("title", "")
        return SearchHit(
            id=hit["_id"],
            score=hit.get("_score"),
            title=title,
            snippet=snippet,
            tags=source.get("tags", []),
            metadata=source.get("metadata", {}),
            highlights=title_highlights + content_highlights,
        )

    def _build_index_name(self, tenant_id: str) -> str:
        safe_tenant = tenant_id.lower().replace("_", "-")
        return f"{self.settings.opensearch_index_prefix}-{safe_tenant}"

    @staticmethod
    def _record_from_source(document_id: str, source: dict[str, Any]) -> DocumentRecord:
        return DocumentRecord(
            id=document_id,
            tenant_id=source["tenant_id"],
            title=source["title"],
            content=source["content"],
            tags=source.get("tags", []),
            metadata=source.get("metadata", {}),
            created_at=source["created_at"],
            updated_at=source["updated_at"],
        )
