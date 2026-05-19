"""BM25 keyword search via PostgreSQL full-text search on document_chunks."""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

from kb_service.config import settings

logger = logging.getLogger(__name__)


class BM25Searcher:
    """Performs BM25 keyword search against document_chunks using PostgreSQL FTS."""

    def __init__(self, pool: asyncpg.Pool | None = None) -> None:
        self._pool = pool

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is not None:
            return self._pool
        self._pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=5)
        return self._pool

    async def search(
        self,
        query: str,
        top_k: int = 50,
        project_id: str | None = None,
        document_ids: list[str] | None = None,
        chunk_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search document_chunks using PostgreSQL FTS.

        Uses ts_rank with the existing GIN index on to_tsvector('simple', content).
        """
        pool = await self._get_pool()

        # Build conditions
        conditions = []
        params: list[Any] = []
        param_idx = 1

        # FTS query — convert natural language to tsquery tokens
        tokens = query.split()
        tsquery = " & ".join(t for t in tokens if t.isalnum())
        if not tsquery:
            tsquery = query
        conditions.append(f"to_tsvector('simple', content) @@ to_tsquery('simple', ${param_idx})")
        params.append(tsquery)
        param_idx += 1

        if project_id:
            conditions.append(f"project_id = ${param_idx}::uuid")
            params.append(project_id)
            param_idx += 1

        if document_ids:
            placeholders = ", ".join(f"${param_idx + i}::uuid" for i in range(len(document_ids)))
            conditions.append(f"document_id IN ({placeholders})")
            params.extend(document_ids)
            param_idx += len(document_ids)

        if chunk_types:
            placeholders = ", ".join(f"${param_idx + i}" for i in range(len(chunk_types)))
            conditions.append(f"chunk_type IN ({placeholders})")
            params.extend(chunk_types)
            param_idx += len(chunk_types)

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT
                id AS chunk_id,
                document_id,
                project_id,
                chunk_type,
                content,
                page_start,
                page_end,
                ts_rank(to_tsvector('simple', content), to_tsquery('simple', $1)) AS bm25_score
            FROM document_chunks
            WHERE {where_clause}
            ORDER BY bm25_score DESC
            LIMIT ${param_idx}
        """
        params.append(top_k)


        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, *params)
        except Exception as exc:
            logger.warning("BM25 search error: %s", exc)
            return []

        return [
            {
                "chunk_id": str(row["chunk_id"]),
                "document_id": str(row["document_id"]),
                "project_id": str(row["project_id"]),
                "chunk_type": row["chunk_type"],
                "content": row["content"],
                "page_start": row["page_start"] or 0,
                "page_end": row["page_end"] or 0,
                "score": float(row["bm25_score"]),
            }
            for row in rows
        ]

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None


class InMemoryBM25Searcher:
    """In-memory BM25 searcher for testing.

    Uses a simple TF-IDF-like scoring against an in-memory chunk store.
    """

    def __init__(self) -> None:
        self._chunks: list[dict[str, Any]] = []

    def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """Add chunks to the in-memory index."""
        self._chunks = chunks

    def remove_by_document(self, document_id: str) -> int:
        before = len(self._chunks)
        self._chunks = [c for c in self._chunks if c.get("document_id") != document_id]
        return before - len(self._chunks)

    def remove_by_project(self, project_id: str) -> int:
        before = len(self._chunks)
        self._chunks = [c for c in self._chunks if c.get("project_id") != project_id]
        return before - len(self._chunks)

    async def search(
        self,
        query: str,
        top_k: int = 50,
        project_id: str | None = None,
        document_ids: list[str] | None = None,
        chunk_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search with simple keyword overlap scoring."""
        query_tokens = set(query.lower().split())

        scored: list[tuple[float, dict[str, Any]]] = []
        for chunk in self._chunks:
            if project_id and chunk.get("project_id") != project_id:
                continue
            if document_ids and chunk.get("document_id") not in document_ids:
                continue
            if chunk_types and chunk.get("chunk_type") not in chunk_types:
                continue

            content_tokens = set(chunk["content"].lower().split())
            if not query_tokens or not content_tokens:
                continue

            overlap = query_tokens & content_tokens
            score = len(overlap) / (len(query_tokens) + len(content_tokens) - len(overlap))
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = scored[:top_k]

        return [
            {
                **chunk,
                "score": score,
            }
            for score, chunk in results
        ]
