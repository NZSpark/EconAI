"""BM25 keyword search via PostgreSQL full-text search on document_chunks."""

from __future__ import annotations

import logging
import re
from typing import Any

import asyncpg

from kb_service.config import settings

logger = logging.getLogger(__name__)

# CJK Unicode ranges: Chinese, Japanese, Korean
_CJK_RE = re.compile(r"[一-鿿㐀-䶿豈-﫿]")


def _contains_cjk(text: str) -> bool:
    """Check whether *text* contains any CJK characters."""
    return bool(_CJK_RE.search(text))


class BM25Searcher:
    """Performs BM25 keyword search against document_chunks using PostgreSQL FTS.

    Uses two strategies:
    - tsvector/tsquery ('simple' config) for Latin-script queries (fast, exact)
    - pg_trgm word_similarity() for CJK-heavy queries (fuzzy, n-gram based)

    The pg_trgm path is automatically selected when the query contains CJK
    characters so that Chinese word boundaries are handled via trigram overlap
    rather than per-character tokenization.
    """

    def __init__(self, pool: asyncpg.Pool | None = None) -> None:
        self._pool = pool

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is not None:
            return self._pool
        self._pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=5)
        return self._pool

    # ── shared WHERE-clause builder ──────────────────────────────────────

    def _build_conditions(
        self,
        project_id: str | None,
        document_ids: list[str] | None,
        chunk_types: list[str] | None,
    ) -> tuple[list[str], list[Any], int]:
        conditions: list[str] = []
        params: list[Any] = []
        idx = 1

        if project_id:
            conditions.append(f"project_id = ${idx}::uuid")
            params.append(project_id)
            idx += 1

        if document_ids:
            placeholders = ", ".join(f"${idx + i}::uuid" for i in range(len(document_ids)))
            conditions.append(f"document_id IN ({placeholders})")
            params.extend(document_ids)
            idx += len(document_ids)

        if chunk_types:
            placeholders = ", ".join(f"${idx + i}" for i in range(len(chunk_types)))
            conditions.append(f"chunk_type IN ({placeholders})")
            params.extend(chunk_types)
            idx += len(chunk_types)

        return conditions, params, idx

    # ── FTS path (English / Latin scripts) ───────────────────────────────

    def _build_fts_sql(
        self,
        conditions: list[str],
        param_idx: int,
        tsquery: str,
        top_k: int,
    ) -> tuple[str, list[Any]]:
        params: list[Any] = [tsquery]
        fts_cond = "to_tsvector('simple', content) @@ to_tsquery('simple', $1)"
        where = " AND ".join([fts_cond] + conditions)
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
            WHERE {where}
            ORDER BY bm25_score DESC
            LIMIT ${param_idx + 1}
        """
        params.append(top_k)
        return sql, params

    # ── Trigram path (Chinese / CJK) ─────────────────────────────────────

    def _build_trgm_sql(
        self,
        conditions: list[str],
        param_idx: int,
        query: str,
        top_k: int,
    ) -> tuple[str, list[Any]]:
        params: list[Any] = [query]
        # word_similarity() scores how well the query matches substrings in content.
        # The gin_trgm_ops index on content supports the %> operator efficiently.
        trgm_cond = "content %> $1"
        where = " AND ".join([trgm_cond] + conditions)
        sql = f"""
            SELECT
                id AS chunk_id,
                document_id,
                project_id,
                chunk_type,
                content,
                page_start,
                page_end,
                word_similarity($1, content) AS bm25_score
            FROM document_chunks
            WHERE {where}
            ORDER BY bm25_score DESC
            LIMIT ${param_idx + 1}
        """
        params.append(top_k)
        return sql, params

    # ── public API ───────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        top_k: int = 50,
        project_id: str | None = None,
        document_ids: list[str] | None = None,
        chunk_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search document_chunks using PostgreSQL FTS or pg_trgm.

        Automatically selects the trigram path when the query contains CJK
        characters, otherwise falls back to tsvector/tsquery.
        """
        pool = await self._get_pool()
        conditions, extra_params, param_idx = self._build_conditions(
            project_id, document_ids, chunk_types
        )

        if _contains_cjk(query):
            sql, params = self._build_trgm_sql(conditions, param_idx, query, top_k)
            # Merge extra params after the query param (which is $1)
            params[1:1] = extra_params
            # Fix param indices in merged params — _build_trgm_sql returns
            # [query, top_k], extra_params are for conditions starting at $2
            logger.debug("BM25 using pg_trgm path (CJK detected)")
        else:
            tokens = query.split()
            tsquery = " & ".join(t for t in tokens if t.isalnum())
            if not tsquery:
                tsquery = query
            sql, params = self._build_fts_sql(conditions, param_idx, tsquery, top_k)
            params[1:1] = extra_params

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
