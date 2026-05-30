""" 向量存储。"""

from __future__ import annotations

import logging
from typing import Any

from kb_service.config import settings
from kb_service.vector_store import VectorStore

logger = logging.getLogger(__name__)


class MilvusVectorStore(VectorStore):
    """Vector store backed by Milvus."""

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
        self._connected = False

    async def _ensure_connected(self) -> None:
        if self._connected:
            return
        try:
            from pymilvus import (
                Collection,
                DataType,
                MilvusClient,
                connections,
            )

            connections.connect(host=self._host, port=str(self._port))
            self._client = MilvusClient(uri=f"http://{self._host}:{self._port}")

            if not self._client.has_collection(self._collection_name):
                schema = self._client.create_schema(
                    auto_id=False,
                    enable_dynamic_field=False,
                )
                schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=64)
                schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=self._dim)
                schema.add_field(field_name="document_id", datatype=DataType.VARCHAR, max_length=64)
                schema.add_field(field_name="project_id", datatype=DataType.VARCHAR, max_length=64)
                schema.add_field(field_name="chunk_type", datatype=DataType.VARCHAR, max_length=16)
                schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=65535)

                index_params = self._client.prepare_index_params()
                index_params.add_index(
                    field_name="vector",
                    index_type="IVF_FLAT",
                    metric_type="IP",
                    params={"nlist": 128},
                )

                self._client.create_collection(
                    collection_name=self._collection_name,
                    schema=schema,
                    index_params=index_params,
                )

            self._collection = Collection(self._collection_name)
            self._collection.load()
            self._connected = True
            logger.info("Connected to Milvus: %s:%d, collection=%s", self._host, self._port, self._collection_name)
        except ImportError:
            logger.error("pymilvus not installed")
            raise
        except Exception:
            logger.exception("Failed to connect to Milvus")
            raise

    async def create_collection(self) -> None:
        await self._ensure_connected()

    async def insert(
        self,
        chunk_id: str,
        vector: list[float],
        metadata: dict[str, Any],
    ) -> None:
        await self._ensure_connected()
        self._client.insert(
            collection_name=self._collection_name,
            data=[{
                "id": chunk_id,
                "vector": vector,
                "document_id": metadata.get("document_id", ""),
                "project_id": metadata.get("project_id", ""),
                "chunk_type": metadata.get("chunk_type", "paragraph"),
                "content": metadata.get("content", ""),
            }],
        )
        self._client.flush(collection_name=self._collection_name)

    async def insert_batch(
        self,
        entries: list[tuple[str, list[float], dict[str, Any]]],
    ) -> None:
        await self._ensure_connected()
        data = [
            {
                "id": chunk_id,
                "vector": vector,
                "document_id": meta.get("document_id", ""),
                "project_id": meta.get("project_id", ""),
                "chunk_type": meta.get("chunk_type", "paragraph"),
                "content": meta.get("content", ""),
            }
            for chunk_id, vector, meta in entries
        ]
        self._client.insert(collection_name=self._collection_name, data=data)
        self._client.flush(collection_name=self._collection_name)

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 50,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        await self._ensure_connected()
        filter_expr = self._build_filter(filters)
        results = self._client.search(
            collection_name=self._collection_name,
            data=[query_vector],
            limit=top_k,
            filter=filter_expr or None,
            output_fields=["document_id", "project_id", "chunk_type", "content"],
        )
        if not results or not results[0]:
            return []
        return [
            {
                "chunk_id": hit["id"],
                "score": hit["distance"],
                "metadata": {
                    "document_id": hit.get("entity", {}).get("document_id", ""),
                    "project_id": hit.get("entity", {}).get("project_id", ""),
                    "chunk_type": hit.get("entity", {}).get("chunk_type", ""),
                    "content": hit.get("entity", {}).get("content", ""),
                },
            }
            for hit in results[0]
        ]

    async def delete_by_document(self, document_id: str) -> int:
        await self._ensure_connected()
        result = self._client.delete(
            collection_name=self._collection_name,
            filter=f'document_id == "{document_id}"',
        )
        return len(result) if result else 0

    async def delete_by_project(self, project_id: str) -> int:
        await self._ensure_connected()
        result = self._client.delete(
            collection_name=self._collection_name,
            filter=f'project_id == "{project_id}"',
        )
        return len(result) if result else 0

    @staticmethod
    def _build_filter(filters: dict[str, Any] | None) -> str | None:
        if not filters:
            return None
        parts: list[str] = []
        for key, value in filters.items():
            if isinstance(value, list):
                in_values = ", ".join(f'"{v}"' for v in value)
                parts.append(f"{key} in [{in_values}]")
            else:
                parts.append(f'{key} == "{value}"')
        return " and ".join(parts) if parts else None
