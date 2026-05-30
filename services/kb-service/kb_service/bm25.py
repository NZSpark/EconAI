"""BM25 keyword search via PostgreSQL full-text search on document_chunks."""

from __future__ import annotations

import logging
import os
from typing import Any

import asyncpg

from kb_service.config import settings
from kb_service.tokenizer import contains_cjk, tokenize

logger = logging.getLogger(__name__)


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
        # Use KB_DATABASE_URL env var directly because the AppSettings property
        # for database_url is computed from postgres_host (always localhost).
        # Convert SQLAlchemy DSN (postgresql+asyncpg://) to asyncpg format (postgresql://).
        db_url = os.getenv("KB_DATABASE_URL", settings.database_url)
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        self._pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
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
            conditions.append(f"dc.project_id = ${idx}::uuid")
            params.append(project_id)
            idx += 1

        if document_ids:
            placeholders = ", ".join(f"${idx + i}::uuid" for i in range(len(document_ids)))
            conditions.append(f"dc.document_id IN ({placeholders})")
            params.extend(document_ids)
            idx += len(document_ids)

        if chunk_types:
            placeholders = ", ".join(f"${idx + i}" for i in range(len(chunk_types)))
            conditions.append(f"dc.chunk_type IN ({placeholders})")
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
        import re as _re

        params: list[Any] = [tsquery]
        fts_cond = "to_tsvector('simple', content) @@ to_tsquery('simple', $1)"
        # Re-number condition placeholders: $N → $(N+1) because $1 is the tsquery
        shifted = [_re.sub(r'\$(\d+)', lambda m: f'${int(m.group(1)) + 1}', c) for c in conditions]
        where = " AND ".join([fts_cond] + shifted)
        sql = f"""
            SELECT
                dc.id AS chunk_id,
                dc.document_id,
                dc.project_id,
                dc.chunk_type,
                dc.content,
                dc.page_start,
                dc.page_end,
                d.title AS document_title,
                d.filename AS document_filename,
                ts_rank(to_tsvector('simple', dc.content), to_tsquery('simple', $1)) AS bm25_score
            FROM document_chunks dc
            LEFT JOIN documents d ON dc.document_id = d.id
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
        import re as _re

        params: list[Any] = [query]
        # word_similarity() scores how well the query matches substrings in content.
        # The gin_trgm_ops index on content supports the %> operator efficiently.
        trgm_cond = "content %> $1"
        # Re-number condition placeholders: $N → $(N+1) because $1 is the query
        shifted = [_re.sub(r'\$(\d+)', lambda m: f'${int(m.group(1)) + 1}', c) for c in conditions]
        where = " AND ".join([trgm_cond] + shifted)
        sql = f"""
            SELECT
                dc.id AS chunk_id,
                dc.document_id,
                dc.project_id,
                dc.chunk_type,
                dc.content,
                dc.page_start,
                dc.page_end,
                d.title AS document_title,
                d.filename AS document_filename,
                word_similarity($1, dc.content) AS bm25_score
            FROM document_chunks dc
            LEFT JOIN documents d ON dc.document_id = d.id
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

        if contains_cjk(query):
            # Try jieba tokenization first for better precision with FTS.
            # If jieba produces usable tokens, use tsquery; otherwise fall
            # back to pg_trgm fuzzy matching.
            tokens = tokenize(query)
            tsquery = " & ".join(t for t in tokens if t.isalnum())
            if tsquery:
                sql, params = self._build_fts_sql(conditions, param_idx, tsquery, top_k)
                params[1:1] = extra_params
                logger.debug("BM25 using FTS path (CJK + jieba tokens)")
            else:
                sql, params = self._build_trgm_sql(conditions, param_idx, query, top_k)
                params[1:1] = extra_params
                logger.debug("BM25 using pg_trgm fallback (CJK, no jieba tokens)")
        else:
            tokens = tokenize(query)
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
                "document_title": row.get("document_title") or "",
                "document_filename": row.get("document_filename") or "",
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
        """Search with simple keyword overlap scoring.

        Uses tokenize() for Chinese-aware tokenization so that both
        Chinese and English queries produce meaningful token sets.
        """
        from kb_service.tokenizer import tokenize

        query_tokens = set(t.lower() for t in tokenize(query))

        scored: list[tuple[float, dict[str, Any]]] = []
        for chunk in self._chunks:
            if project_id and chunk.get("project_id") != project_id:
                continue
            if document_ids and chunk.get("document_id") not in document_ids:
                continue
            if chunk_types and chunk.get("chunk_type") not in chunk_types:
                continue

            content_tokens = set(t.lower() for t in tokenize(chunk["content"]))
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
