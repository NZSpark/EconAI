"""EconAI Knowledge Base Service (M3) — FastAPI application.

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
    title="EconAI Knowledge Base Service",
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


def _build_result(
    chunk: dict[str, Any],
    document_titles: dict[str, str] | None = None,
) -> ChunkResult:
    """Format a search hit into a ChunkResult."""
    doc_id = chunk.get("document_id", "")
    titles = document_titles or {}
    return ChunkResult(
        chunk_id=chunk.get("chunk_id", ""),
        document_id=doc_id,
        document_title=titles.get(doc_id, ""),
        content=chunk.get("content", ""),
        chunk_type=chunk.get("chunk_type", "paragraph"),
        score=round(chunk.get("score", 0.0), 4),
        metadata={
            "page_start": chunk.get("metadata", {}).get("page_start", 0),
            "page_end": chunk.get("metadata", {}).get("page_end", 0),
            "section_title": chunk.get("metadata", {}).get("section_title", ""),
        },
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
    )

    return SearchResponse(
        results=[_build_result(r) for r in results],
        total_hits=total_hits,
        search_time_ms=round(search_time_ms, 2),
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
    )

    return SearchResponse(
        results=[_build_result(r) for r in results],
        total_hits=total_hits,
        search_time_ms=round(search_time_ms, 2),
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
    )

    return SearchResponse(
        results=[_build_result(r) for r in results],
        total_hits=total_hits,
        search_time_ms=round(search_time_ms, 2),
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
