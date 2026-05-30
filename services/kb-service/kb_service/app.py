"""PolicyAI Knowledge Base Service (M3) — FastAPI application.

Port 8002. Provides:
  - GET  /health                              Health check
  - POST /api/projects/{project_id}/search    Project KB search
  - POST /api/institutional/search            Institutional KB search
  - POST /internal/search                     Internal search (for orchestration)
  - POST /internal/index                      Index chunks (for document-service callback)
  - POST /internal/index/reindex              Reindex a document
  - DELETE /internal/index/document/{id}      Delete document index
  - DELETE /internal/index/project/{id}       Delete project index
  - POST /internal/lifecycle/archive/document/{id}   Archive document
  - POST /internal/lifecycle/restore/document/{id}   Restore document
  - POST /internal/lifecycle/archive/project/{id}    Archive project
  - POST /internal/lifecycle/restore/project/{id}    Restore project
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from kb_service.config import settings
from kb_service.deps import create_bm25_searcher, create_embedding_client, create_vector_store
from kb_service.hybrid_search import HybridSearcher
from kb_service.indexer import IndexPipeline
from kb_service.lifecycle import LifecycleManager
from kb_service.schemas import (
    ChunkResult,
    IndexStatusResponse,
    InternalSearchRequest,
    SearchRequest,
    SearchResponse,
)
from shared.metrics import setup_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Global state
_searcher: HybridSearcher
_pipeline: IndexPipeline
_lifecycle: LifecycleManager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _searcher, _pipeline, _lifecycle

    logger.info("KB Service starting up...")

    _vector_store = create_vector_store()
    _embedding = create_embedding_client()
    _bm25 = create_bm25_searcher()
    _searcher = HybridSearcher(
        vector_store=_vector_store,
        embedding_client=_embedding,
        bm25_searcher=_bm25,
    )
    _pipeline = IndexPipeline(
        vector_store=_vector_store,
        embedding_client=_embedding,
        bm25_searcher=_bm25,
    )
    _lifecycle = LifecycleManager(_pipeline)

    logger.info("KB Service ready on port %d, embedding_dim=%d", settings.service_port, settings.embedding_dim)

    yield

    logger.info("KB Service shutting down.")


app = FastAPI(
    title="PolicyAI Knowledge Base Service",
    version="0.1.0",
    lifespan=lifespan,
)

setup_metrics(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ──────────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict[str, object]:
    """Health check — reports service status and initialized components."""
    deps_status: dict[str, str] = {}
    deps_status["hybrid_searcher"] = "initialized" if _searcher is not None else "missing"
    deps_status["index_pipeline"] = "initialized" if _pipeline is not None else "missing"
    deps_status["lifecycle_manager"] = "initialized" if _lifecycle is not None else "missing"

    return {
        "status": "healthy" if all(v == "initialized" for v in deps_status.values()) else "degraded",
        "service": "kb-service",
        "config": {
            "vector_db_type": settings.vector_db_type,
            "embedding_dim": settings.embedding_dim,
            "embedding_model": settings.embedding_model,
            "reranker_enabled": settings.reranker_enabled,
        },
        "dependencies": deps_status,
    }


# ── Permission helpers ──────────────────────────────────────────────────────


def _check_project_access(project_id: str) -> None:
    """Verify that the caller has access to the project KB.

    In production this checks JWT user context against project members.
    For now, skips check when no auth context is available (internal calls).
    """
    # If archived, deny search
    if LifecycleManager.is_archived(project_id):
        raise HTTPException(status_code=403, detail="Project is archived")


async def _fetch_document_titles(
    doc_ids: set[str],
    project_id: str | None = None,
) -> dict[str, str]:
    """Batch-fetch document display names from the documents table.

    Uses original_name (the user-visible filename with extension) so the
    frontend always shows the complete file name.
    Falls back to document_id itself if no database row is found.
    """
    if not doc_ids:
        return {}

    import os

    import asyncpg

    db_url = os.getenv("KB_DATABASE_URL", settings.database_url)
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        conn = await asyncpg.connect(db_url)
        try:
            rows = await conn.fetch(
                """
                SELECT id, original_name AS display_name
                FROM documents
                WHERE id = ANY($1::uuid[])
                """,
                list(doc_ids),
            )
            title_map = {str(r["id"]): r["display_name"] for r in rows}
        finally:
            await conn.close()
    except Exception as exc:
        logger.warning("Failed to fetch document titles: %s", exc)
        title_map = {}

    # Fallback: any doc_id not found in DB → use the doc_id itself
    for did in doc_ids:
        if did not in title_map:
            title_map[did] = did
    return title_map


def _build_result(
    chunk: dict[str, Any],
    query: str = "",
    document_titles: dict[str, str] | None = None,
) -> ChunkResult:
    """Format a search hit into a ChunkResult.

    When *query* is provided, matched_terms and highlighted_content are
    generated via the tokenizer so the frontend can render keyword
    highlights without re-tokenizing.
    """
    from kb_service.tokenizer import apply_highlight, extract_matched_terms, find_highlight_spans

    doc_id = chunk.get("document_id", "")
    content = chunk.get("content", "")

    matched_terms: list[str] = []
    highlighted_content = ""
    if query:
        matched_terms = extract_matched_terms(query)
        spans = find_highlight_spans(content, query)
        highlighted_content = apply_highlight(content, spans)

    # Prefer the actual document title from the joined query (BM25 path);
    # then from the batch-fetched title map; finally fall back to document_id.
    titles = document_titles or {}
    doc_title = chunk.get("document_title") or titles.get(doc_id) or doc_id

    # page_start / page_end may come from the chunk root (BM25 path) or
    # from the metadata sub-dict (vector path).
    meta = chunk.get("metadata", {})
    page_start = chunk.get("page_start") or meta.get("page_start", 0)
    page_end = chunk.get("page_end") or meta.get("page_end", 0)
    section_title = chunk.get("section_title") or meta.get("section_title", "")

    return ChunkResult(
        chunk_id=chunk.get("chunk_id", ""),
        document_id=doc_id,
        document_title=doc_title,
        content=content,
        chunk_type=chunk.get("chunk_type", "paragraph"),
        score=round(chunk.get("score", 0.0), 4),
        metadata={
            "page_start": page_start,
            "page_end": page_end,
            "section_title": section_title,
        },
        matched_terms=matched_terms,
        highlighted_content=highlighted_content,
    )


# ── Public API ──────────────────────────────────────────────────────────────


@app.post("/api/projects/{project_id}/search", response_model=SearchResponse)
async def search_project(project_id: str, body: SearchRequest) -> SearchResponse:
    """Search within a project's knowledge base."""
    _check_project_access(project_id)

    results, total_hits, search_time_ms = await _searcher.search(
        query=body.query,
        top_k=body.top_k,
        project_id=project_id,
        document_ids=body.filters.document_ids or None,
        chunk_types=body.filters.chunk_types or None,
        search_mode=body.search_mode,
        page=body.page,
        page_size=body.page_size,
    )

    doc_ids = {r.get("document_id", "") for r in results if r.get("document_id")}
    titles = await _fetch_document_titles(doc_ids, project_id)

    total_pages = max(1, (total_hits + body.page_size - 1) // body.page_size) if total_hits else 1

    return SearchResponse(
        results=[_build_result(r, query=body.query, document_titles=titles) for r in results],
        total_hits=total_hits,
        search_time_ms=round(search_time_ms, 2),
        page=body.page,
        page_size=body.page_size,
        pages=total_pages,
    )


@app.post("/api/institutional/search", response_model=SearchResponse)
async def search_institutional(body: SearchRequest) -> SearchResponse:
    """Search across the institutional knowledge base (all authorized projects)."""
    results, total_hits, search_time_ms = await _searcher.search(
        query=body.query,
        top_k=body.top_k,
        project_id=None,  # cross-project search
        document_ids=body.filters.document_ids or None,
        chunk_types=body.filters.chunk_types or None,
        search_mode=body.search_mode,
        page=body.page,
        page_size=body.page_size,
    )

    doc_ids = {r.get("document_id", "") for r in results if r.get("document_id")}
    titles = await _fetch_document_titles(doc_ids)

    total_pages = max(1, (total_hits + body.page_size - 1) // body.page_size) if total_hits else 1

    return SearchResponse(
        results=[_build_result(r, query=body.query, document_titles=titles) for r in results],
        total_hits=total_hits,
        search_time_ms=round(search_time_ms, 2),
        page=body.page,
        page_size=body.page_size,
        pages=total_pages,
    )


# ── Internal API ────────────────────────────────────────────────────────────


@app.post("/internal/search", response_model=SearchResponse)
async def internal_search(body: InternalSearchRequest) -> SearchResponse:
    """Internal search endpoint for orchestration-service.

    Includes additional auth context (project_id, group_ids).
    """
    project_id = body.project_id

    if project_id:
        _check_project_access(project_id)

    results, total_hits, search_time_ms = await _searcher.search(
        query=body.query,
        top_k=body.top_k,
        project_id=project_id,
        document_ids=body.filters.document_ids or None,
        chunk_types=body.filters.chunk_types or None,
        search_mode=body.search_mode,
        page=body.page,
        page_size=body.page_size,
    )

    doc_ids = {r.get("document_id", "") for r in results if r.get("document_id")}
    titles = await _fetch_document_titles(doc_ids, project_id)

    total_pages = max(1, (total_hits + body.page_size - 1) // body.page_size) if total_hits else 1

    return SearchResponse(
        results=[_build_result(r, query=body.query, document_titles=titles) for r in results],
        total_hits=total_hits,
        search_time_ms=round(search_time_ms, 2),
        page=body.page,
        page_size=body.page_size,
        pages=total_pages,
    )


@app.post("/internal/index", response_model=IndexStatusResponse)
async def index_chunks(body: dict[str, Any]) -> IndexStatusResponse:
    """Index a batch of chunks. Called by document-service after parsing."""
    chunks = body.get("chunks", [])
    if not chunks:
        raise HTTPException(status_code=400, detail="No chunks provided")

    count = await _pipeline.index_chunks(chunks)
    return IndexStatusResponse(status="indexed", message=f"Indexed {count} chunks", indexed_chunks=count)


@app.post("/internal/index/reindex", response_model=IndexStatusResponse)
async def reindex_chunks(body: dict[str, Any]) -> IndexStatusResponse:
    """Reindex chunks for a document (delete existing, then index)."""
    chunks = body.get("chunks", [])
    if not chunks:
        raise HTTPException(status_code=400, detail="No chunks provided")

    count = await _pipeline.reindex_chunks(chunks)
    return IndexStatusResponse(status="reindexed", message=f"Reindexed {count} chunks", indexed_chunks=count)


@app.delete("/internal/index/document/{document_id}")
async def delete_document_index(document_id: str) -> dict[str, Any]:
    """Delete all index entries for a document."""
    count = await _pipeline.delete_document(document_id)
    return {"status": "deleted", "document_id": document_id, "deleted_vectors": count}


@app.delete("/internal/index/project/{project_id}")
async def delete_project_index(project_id: str) -> dict[str, Any]:
    """Delete all index entries for a project."""
    count = await _pipeline.delete_project(project_id)
    return {"status": "deleted", "project_id": project_id, "deleted_vectors": count}


# ── Lifecycle endpoints ─────────────────────────────────────────────────────


@app.post("/internal/lifecycle/archive/document/{document_id}")
async def archive_document(document_id: str) -> dict[str, str]:
    return await _lifecycle.archive_document(document_id)


@app.post("/internal/lifecycle/restore/document/{document_id}")
async def restore_document(document_id: str) -> dict[str, str]:
    return await _lifecycle.restore_document(document_id)


@app.post("/internal/lifecycle/archive/project/{project_id}")
async def archive_project(project_id: str) -> dict[str, str]:
    return await _lifecycle.archive_project(project_id)


@app.post("/internal/lifecycle/restore/project/{project_id}")
async def restore_project(project_id: str) -> dict[str, str]:
    return await _lifecycle.restore_project(project_id)


# ── Exception handlers ──────────────────────────────────────────────────────


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"KB_{'CLIENT' if exc.status_code < 500 else 'SERVER'}_ERROR",
                "message": exc.detail,
            }
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception in KB Service")
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "KB_INTERNAL_ERROR", "message": "An internal error occurred. Please try later."}},
    )
