"""Async PostgreSQL database layer for the Document Service.

When PostgreSQL is available (Docker deployment), uses SQLAlchemy async ORM
for persistent storage across restarts. Falls back to in-memory dicts when
the DB is unavailable (e.g., test environments without Docker).

Uses asyncpg driver already declared in pyproject.toml.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import MetaData, Table, and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql import insert, update, delete

from document_service.config import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory fallback (used when PostgreSQL is not available)
# ---------------------------------------------------------------------------

_in_memory_docs: dict[str, dict[str, Any]] = {}
_in_memory_chunks: dict[str, list[dict[str, Any]]] = {}

# ---------------------------------------------------------------------------
# DB availability flag — set by init_db()
# ---------------------------------------------------------------------------

db_available = False

# ---------------------------------------------------------------------------
# Engine & session factory (initialized in init_db)
# ---------------------------------------------------------------------------

engine = None
async_session_factory = None
_metadata = MetaData()
_documents_tbl: Table | None = None
_document_chunks_tbl: Table | None = None


# ---------------------------------------------------------------------------
# Init: create engine and verify PostgreSQL connectivity
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """初始化 database connection or fall back to in-memory store. Called at startup."""
    global db_available, engine, async_session_factory

    try:
        engine = create_async_engine(
            config.DATABASE_URL,
            echo=False,
            pool_size=10,
            max_overflow=5,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.commit()

        async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        # Reflect existing tables using async engine
        await _tbls_async()
        db_available = True
        logger.info("PostgreSQL connection established; document persistence ENABLED")
    except Exception as e:
        db_available = False
        engine = None
        async_session_factory = None
        logger.warning(
            "PostgreSQL not available at %s (%s: %s); "
            "falling back to IN-MEMORY store (documents will be lost on restart)",
            config.DATABASE_URL,
            type(e).__name__,
            e,
        )


async def _tbls_async() -> tuple[Table, Table]:
    """Reflect and return document tables (async-safe). Must be called after engine init."""
    global _documents_tbl, _document_chunks_tbl, engine
    if engine is None:
        raise RuntimeError("Database engine not initialized")
    if _documents_tbl is None:
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: _metadata.reflect(bind=sync_conn, only=["documents"])
            )
        _documents_tbl = _metadata.tables["documents"]
    if _document_chunks_tbl is None:
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: _metadata.reflect(bind=sync_conn, only=["document_chunks"])
            )
        _document_chunks_tbl = _metadata.tables["document_chunks"]
    return _documents_tbl, _document_chunks_tbl


def _tbls() -> tuple[Table, Table]:
    """Sync wrapper for table reflection. Use _tbls_async() in async contexts."""
    global _documents_tbl, _document_chunks_tbl
    if _documents_tbl is not None and _document_chunks_tbl is not None:
        return _documents_tbl, _document_chunks_tbl
    raise RuntimeError("Tables not reflected yet; call _tbls_async() at startup first")


# ===========================================================================
# Public API — each function automatically uses DB or in-memory fallback
# ===========================================================================
#
# All async functions below accept AsyncSession. When db_available=True the
# session is a real DB session; when False it is None and in-memory fallback
# is used transparently.
#
# Callers should use:
#     if db_available:
#         async with async_session_factory() as session:
#             await insert_document(session, ...)
#     else:
#         await insert_document(None, ...)   # falls back to in-memory
#
# Or, for simplicity, the functions accept session=None as fallback trigger.
# ===========================================================================

# ---------------------------------------------------------------------------
# Document repository
# ---------------------------------------------------------------------------

async def insert_document(
    session: AsyncSession | None,
    *,
    doc_id: str,
    project_id: str,
    filename: str,
    original_name: str,
    fmt: str,
    size_bytes: int,
    storage_path: str,
    is_internal: bool,
    title: str | None = None,
) -> None:
    """插入 a new document record with parse_status='pending'."""
    now = datetime.now(UTC)
    if db_available and session is not None:
        docs, _ = await _tbls_async()
        await session.execute(
            insert(docs).values(
                id=doc_id,
                project_id=project_id,
                filename=storage_path,
                original_name=original_name,
                format=fmt,
                size_bytes=size_bytes,
                storage_path=storage_path,
                parse_status="pending",
                is_internal=is_internal,
                title=title,
                page_count=0,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
    else:
        _in_memory_docs[doc_id] = {
            "id": doc_id,
            "project_id": project_id,
            "filename": storage_path,
            "original_name": original_name,
            "format": fmt,
            "size_bytes": size_bytes,
            "storage_path": storage_path,
            "parse_status": "pending",
            "page_count": 0,
            "metadata": {},
            "is_internal": is_internal,
            "parse_error": None,
            "created_at": now,
            "updated_at": now,
        }


async def update_document_status(
    session: AsyncSession | None,
    doc_id: str,
    status: str,
    *,
    parse_error: str | None = None,
    page_count: int | None = None,
    title: str | None = None,
    author: str | None = None,
) -> None:
    """更新 parse_status and optionally error / page_count / metadata."""
    now = datetime.now(UTC)
    if db_available and session is not None:
        docs, _ = await _tbls_async()
        values: dict[str, Any] = {"parse_status": status, "updated_at": now}
        if parse_error is not None:
            values["parse_error"] = parse_error
        if page_count is not None:
            values["page_count"] = page_count
        if title is not None:
            values["title"] = title
        if author is not None:
            values["author"] = author
        await session.execute(
            update(docs).where(docs.c.id == doc_id).values(**values)
        )
        await session.commit()
    elif doc_id in _in_memory_docs:
        _in_memory_docs[doc_id]["parse_status"] = status
        _in_memory_docs[doc_id]["updated_at"] = now
        if parse_error is not None:
            _in_memory_docs[doc_id]["parse_error"] = parse_error
        if page_count is not None:
            _in_memory_docs[doc_id]["page_count"] = page_count
        if title is not None:
            _in_memory_docs[doc_id].setdefault("metadata", {})["title"] = title
        if author is not None:
            _in_memory_docs[doc_id].setdefault("metadata", {})["authors"] = author


async def get_document(session: AsyncSession | None, doc_id: str) -> dict[str, Any] | None:
    """Return a document dict (keys match the old in-memory format) or None."""
    if db_available and session is not None:
        docs, chunks_tbl = await _tbls_async()
        result = await session.execute(select(docs).where(docs.c.id == doc_id))
        row = result.mappings().first()
        if row is None:
            return None
        chunk_count_result = await session.execute(
            select(func.count()).select_from(chunks_tbl).where(chunks_tbl.c.document_id == doc_id)
        )
        chunk_count = chunk_count_result.scalar() or 0
        doc = dict(row)
        doc["id"] = str(doc["id"])
        doc["project_id"] = str(doc["project_id"])
        doc["chunk_count"] = chunk_count
        doc["metadata"] = {}
        if doc.get("title"):
            doc["metadata"]["title"] = doc["title"]
        if doc.get("author"):
            doc["metadata"]["author"] = doc["author"]
        return doc
    return _in_memory_docs.get(doc_id)


async def list_project_documents(
    session: AsyncSession | None,
    project_id: str,
    *,
    status: str | None = None,
    doc_format: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """Return (items, total_count) for a project's documents."""
    if db_available and session is not None:
        docs, chunks_tbl = await _tbls_async()
        conditions = [docs.c.project_id == project_id]
        if status:
            conditions.append(docs.c.parse_status == status)
        if doc_format:
            conditions.append(docs.c.format == doc_format)
        count_result = await session.execute(
            select(func.count()).select_from(docs).where(and_(*conditions))
        )
        total = count_result.scalar() or 0
        query = (
            select(docs)
            .where(and_(*conditions))
            .order_by(docs.c.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(query)
        rows = result.mappings().all()
        items: list[dict[str, Any]] = []
        for row in rows:
            doc = dict(row)
            doc_id = str(doc["id"])
            ch_result = await session.execute(
                select(func.count()).select_from(chunks_tbl).where(chunks_tbl.c.document_id == doc_id)
            )
            chunk_count = ch_result.scalar() or 0
            doc["id"] = doc_id
            doc["project_id"] = str(doc["project_id"])
            doc["chunk_count"] = chunk_count
            doc["metadata"] = {}
            if doc.get("title"):
                doc["metadata"]["title"] = doc["title"]
            if doc.get("author"):
                doc["metadata"]["authors"] = doc["author"]
            items.append(doc)
        return items, total

    # In-memory fallback
    items = [doc for doc in _in_memory_docs.values() if doc["project_id"] == project_id]
    if status:
        items = [d for d in items if d["parse_status"] == status]
    if doc_format:
        items = [d for d in items if d["format"] == doc_format]
    items.sort(key=lambda d: d["created_at"], reverse=True)  # type: ignore[arg-type,return-value]
    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start:start + page_size]
    return page_items, total


async def delete_document_db(session: AsyncSession | None, doc_id: str) -> None:
    """删除 document and cascade chunks."""
    if db_available and session is not None:
        docs, chunks_tbl = await _tbls_async()
        await session.execute(delete(chunks_tbl).where(chunks_tbl.c.document_id == doc_id))
        await session.execute(delete(docs).where(docs.c.id == doc_id))
        await session.commit()
    else:
        _in_memory_docs.pop(doc_id, None)
        _in_memory_chunks.pop(doc_id, None)


# ---------------------------------------------------------------------------
# Chunk repository
# ---------------------------------------------------------------------------


async def insert_chunks(session: AsyncSession | None, chunks: list[dict[str, Any]]) -> None:
    """插入 processed chunks."""
    if not chunks:
        return
    if db_available and session is not None:
        _, chunks_tbl = await _tbls_async()
        rows = []
        for c in chunks:
            rows.append({
                "id": c.get("id", ""),
                "document_id": c["document_id"],
                "project_id": c["project_id"],
                "chunk_type": c.get("chunk_type", "paragraph"),
                "chunk_index": c.get("chunk_index", 0),
                "content": c.get("chunk_text", c.get("content", "")),
                "token_count": c.get("token_count"),
                "page_start": c.get("page_start"),
                "page_end": c.get("page_end"),
                "embedding_status": "pending",
                "created_at": datetime.now(UTC),
            })
        await session.execute(insert(chunks_tbl), rows)
        await session.commit()
    else:
        doc_id = chunks[0].get("document_id", "") if chunks else ""
        _in_memory_chunks[doc_id] = chunks


async def get_chunks(session: AsyncSession | None, doc_id: str) -> list[dict[str, Any]]:
    """Return all chunks for a document, sorted by chunk_index."""
    if db_available and session is not None:
        _, chunks_tbl = await _tbls_async()
        result = await session.execute(
            select(chunks_tbl)
            .where(chunks_tbl.c.document_id == doc_id)
            .order_by(chunks_tbl.c.chunk_index)
        )
        rows = result.mappings().all()
        return [
            {
                "id": str(r["id"]),
                "document_id": str(r["document_id"]),
                "project_id": str(r["project_id"]),
                "chunk_text": r["content"],
                "chunk_index": r["chunk_index"],
                "token_count": r["token_count"],
                "chunk_type": r["chunk_type"],
                "page_start": r["page_start"],
                "page_end": r["page_end"],
                "section_title": "",
                "paragraph_index": r["chunk_index"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else "",
            }
            for r in rows
        ]
    return _in_memory_chunks.get(doc_id, [])


async def delete_chunks(session: AsyncSession | None, doc_id: str) -> None:
    """删除 all chunks for a document."""
    if db_available and session is not None:
        _, chunks_tbl = await _tbls_async()
        await session.execute(delete(chunks_tbl).where(chunks_tbl.c.document_id == doc_id))
        await session.commit()
    else:
        _in_memory_chunks.pop(doc_id, None)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def reset_in_memory_store() -> None:
    """Clear all in-memory document/chunk state (for test cleanup)."""
    _in_memory_docs.clear()
    _in_memory_chunks.clear()
