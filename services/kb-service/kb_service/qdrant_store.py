"""Qdrant vector store — production implementation using qdrant-client."""

from __future__ import annotations

import logging
from typing import Any

from kb_service.config import settings
from kb_service.vector_store import VectorStore

logger = logging.getLogger(__name__)


class QdrantVectorStore(VectorStore):
    """Vector store backed by Qdrant."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        collection_name: str | None = None,
        dim: int | None = None,
    ) -> None:
        self._host = host or settings.vector_db_host
        self._port = port or settings.vector_db_port
        self._collection_name = collection_name or settings.vector_db_collection
        self._dim = dim or settings.embedding_dim
        self._client: Any = None

    async def _ensure_connected(self) -> None:
        if self._client is not None:
            return
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            self._client = QdrantClient(host=self._host, port=self._port)

            if not self._client.collection_exists(self._collection_name):
                self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
                )

            logger.info("Connected to Qdrant: %s:%d, collection=%s", self._host, self._port, self._collection_name)
        except ImportError:
            logger.error("qdrant-client not installed")
            raise
        except Exception:
            logger.exception("Failed to connect to Qdrant")
            raise

    async def create_collection(self) -> None:
        await self._ensure_connected()

    async def insert(
        self,
        chunk_id: str,
        vector: list[float],
        metadata: dict[str, Any],
    ) -> None:
        from qdrant_client.models import PointStruct

        await self._ensure_connected()
        self._client.upsert(
            collection_name=self._collection_name,
            points=[PointStruct(id=chunk_id, vector=vector, payload=metadata)],
        )

    async def insert_batch(
        self,
        entries: list[tuple[str, list[float], dict[str, Any]]],
    ) -> None:
        from qdrant_client.models import PointStruct

        await self._ensure_connected()
        points = [
            PointStruct(id=chunk_id, vector=vector, payload=meta)
            for chunk_id, vector, meta in entries
        ]
        self._client.upsert(collection_name=self._collection_name, points=points)

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 50,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        await self._ensure_connected()
        qdrant_filter = None
        if filters:
            conditions = [
                FieldCondition(key=key, match=MatchValue(value=value))
                for key, value in filters.items()
                if not isinstance(value, list)
            ]
            if conditions:
                qdrant_filter = Filter(must=conditions)

        results = self._client.search(
            collection_name=self._collection_name,
            query_vector=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
        )
        return [
            {
                "chunk_id": hit.id,
                "score": hit.score,
                "metadata": hit.payload,
            }
            for hit in results
        ]

    async def delete_by_document(self, document_id: str) -> int:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        await self._ensure_connected()
        result = self._client.delete(
            collection_name=self._collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
            ),
        )
        return result.status.get("deleted_count", 0) if result else 0

    async def delete_by_project(self, project_id: str) -> int:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        await self._ensure_connected()
        result = self._client.delete(
            collection_name=self._collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="project_id", match=MatchValue(value=project_id))]
            ),
        )
        return result.status.get("deleted_count", 0) if result else 0
