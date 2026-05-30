"""Vector store — unified interface for Milvus / Qdrant / InMemory."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from kb_service.config import settings

logger = logging.getLogger(__name__)


class VectorStore(ABC):
    """Abstract interface for vector database operations."""

    @abstractmethod
    async def create_collection(self) -> None:
        """创建 collection if it doesn't exist."""
        ...

    @abstractmethod
    async def insert(
        self,
        chunk_id: str,
        vector: list[float],
        metadata: dict[str, Any],
    ) -> None:
        """插入 a single vector with metadata."""
        ...

    @abstractmethod
    async def insert_batch(
        self,
        entries: list[tuple[str, list[float], dict[str, Any]]],
    ) -> None:
        """插入 multiple vectors with metadata."""
        ...

    @abstractmethod
    async def search(
        self,
        query_vector: list[float],
        top_k: int = 50,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """搜索 for nearest neighbors."""
        ...

    @abstractmethod
    async def delete_by_document(self, document_id: str) -> int:
        """删除 all vectors for a document. Returns count deleted."""
        ...

    @abstractmethod
    async def delete_by_project(self, project_id: str) -> int:
        """删除 all vectors for a project. Returns count deleted."""
        ...


class InMemoryVectorStore(VectorStore):
    """In-memory vector store for testing and development.

    Uses cosine similarity for search.
    """

    def __init__(self, dim: int | None = None) -> None:
        self.dim = dim or settings.embedding_dim
        # (chunk_id, vector, metadata)
        self._entries: list[tuple[str, list[float], dict[str, Any]]] = []

    async def create_collection(self) -> None:
        self._entries.clear()

    async def insert(
        self,
        chunk_id: str,
        vector: list[float],
        metadata: dict[str, Any],
    ) -> None:
        self._entries.append((chunk_id, vector, metadata))

    async def insert_batch(
        self,
        entries: list[tuple[str, list[float], dict[str, Any]]],
    ) -> None:
        self._entries.extend(entries)

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 50,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        results: list[tuple[float, int]] = []
        for idx, (chunk_id, vec, meta) in enumerate(self._entries):
            _ = chunk_id
            if not self._matches_filters(meta, filters):
                continue
            sim = self._cosine_similarity(query_vector, vec)
            results.append((sim, idx))

        results.sort(key=lambda x: x[0], reverse=True)
        top = results[:top_k]

        return [
            {
                "chunk_id": self._entries[idx][0],
                "score": score,
                "metadata": self._entries[idx][2],
            }
            for score, idx in top
        ]

    async def delete_by_document(self, document_id: str) -> int:
        before = len(self._entries)
        self._entries = [
            (chunk_id, vec, meta)
            for chunk_id, vec, meta in self._entries
            if meta.get("document_id") != document_id
        ]
        return before - len(self._entries)

    async def delete_by_project(self, project_id: str) -> int:
        before = len(self._entries)
        self._entries = [
            (chunk_id, vec, meta)
            for chunk_id, vec, meta in self._entries
            if meta.get("project_id") != project_id
        ]
        return before - len(self._entries)

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        import math

        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _matches_filters(meta: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True
        for key, value in filters.items():
            if isinstance(value, list):
                if meta.get(key) not in value:
                    return False
            elif meta.get(key) != value:
                return False
        return True
