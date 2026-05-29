"""FastAPI application for the Document Service (M2-04, M2-33 through M2-36).

Endpoints:
  - GET  /health                                              Health check
  - POST /api/projects/{project_id}/documents                  Upload document (M2-04)
  - GET  /api/projects/{project_id}/documents                  List documents (M2-33)
  - GET  /api/projects/{project_id}/documents/{document_id}    Document detail (M2-34)
  - DELETE /api/projects/{project_id}/documents/{document_id}  Delete document (M2-35)
  - POST /api/projects/{project_id}/documents/{document_id}/reindex  Reindex (M2-36)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from fastapi import FastAPI, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from document_service.config import config
import document_service.db as db
from document_service.errors import (
    DocFormatUnsupportedError,
    DocumentNotFoundError,
    ParseError,
)
from document_service.format_identifier import identify_format
from document_service.metadata_extractor import extract_metadata
from document_service.minio_client import delete_file as minio_delete_file
from document_service.minio_client import reset_minio_client, upload_file
from document_service.models import (
    DocumentDetailResponse,
    DocumentListItem,
    DocumentListResponse,
    DocumentUploadResponse,
    HealthResponse,
    ReindexResponse,
)
from document_service.parsers.router import parse_document
from document_service.validation import FileValidationError, validate_file
from shared.metrics import setup_metrics

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="EconAI Document Service",
    version="0.1.0",
    description="Document upload, parsing, chunking, and management (M2).",
)

setup_metrics(app)

# ---------------------------------------------------------------------------
# Session helper: returns a DB session when available, else None (in-memory)
# ---------------------------------------------------------------------------

from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def _get_session():
    """Yield an AsyncSession if DB is available, otherwise None."""
    if db.db_available and db.async_session_factory is not None:
        async with db.async_session_factory() as session:
            yield session
    else:
        yield None


# ---------------------------------------------------------------------------
# Persistent document store (PostgreSQL via async SQLAlchemy)
# ---------------------------------------------------------------------------

# KB Service URL for index callbacks
_KB_SERVICE_URL = os.getenv("KB_SERVICE_URL", "http://kb-service:8002")


async def _index_chunks_in_kb_service(
    document_id: str,
    project_id: str,
    chunk_records: list,
) -> None:
    """Send chunks to KB Service for vector indexing.

    Calls POST /internal/index on the kb-service to trigger embedding
    generation and vector store insertion.
    """
    if not chunk_records:
        logger.warning("No chunks to index for document %s", document_id)
        return

    chunks_payload = [
        {
            "chunk_id": c.chunk_id,
            "document_id": c.document_id,
            "project_id": c.project_id,
            "content": c.chunk_text,
            "chunk_type": c.chunk_type,
            "chunk_index": c.chunk_index,
            "token_count": c.token_count,
            "page_start": c.page_start,
            "page_end": c.page_end,
            "section_title": c.section_title,
        }
        for c in chunk_records
    ]

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{_KB_SERVICE_URL}/internal/index",
                json={"chunks": chunks_payload},
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                "Indexed %s chunks for document %s in KB service (status=%s)",
                data.get("indexed_chunks", 0),
                document_id,
                data.get("status", "unknown"),
            )
    except httpx.HTTPStatusError as exc:
        logger.error(
            "KB service returned error %d for document %s: %s",
            exc.response.status_code,
            document_id,
            exc.response.text[:500] if exc.response.text else "no body",
        )
    except httpx.RequestError as exc:
        logger.error("Failed to reach KB service for document %s: %s", document_id, exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _generate_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Startup: initialize database connection
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def _startup_db() -> None:
    """Reflect DB schema at startup so all workers can use it."""
    await db.init_db()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        service=config.SERVICE_NAME,
        dependencies={
            "minio_endpoint": config.MINIO_ENDPOINT,
            "minio_bucket": config.MINIO_BUCKET,
            "ocr_enabled": config.OCR_ENABLED,
        },
    )


# ---------------------------------------------------------------------------
# M2-04: Upload document
# ---------------------------------------------------------------------------


@app.post(
    "/api/projects/{project_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=201,
    responses={400: {"description": "Validation error"}, 415: {"description": "Unsupported format"}},
)
async def upload_document(
    project_id: str,
    file: UploadFile,
    is_internal: bool = Form(default=False),
    metadata: str | None = Form(default=None),
) -> DocumentUploadResponse:
    """Upload a document for parsing and indexing.

    Validates the file, stores in MinIO, creates a DB record (or in-memory),
    and triggers async processing.
    """
    # Read file content
    file_bytes = await file.read()
    filename = file.filename or "unknown"

    # Parse custom metadata if provided
    custom_meta: dict[str, Any] = {}
    if metadata:
        try:
            custom_meta = json.loads(metadata)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "DOC_INVALID_METADATA", "message": "metadata must be valid JSON."}},
            ) from e

    # Validate file
    try:
        magic = file_bytes[:8]
        ext = validate_file(
            filename=filename,
            mime_type=file.content_type,
            file_size=len(file_bytes),
            magic=magic,
            max_size_mb=config.MAX_FILE_SIZE_MB,
        )
    except FileValidationError as e:
        if e.code == "DOC_FORMAT_UNSUPPORTED":
            raise HTTPException(
                status_code=415,
                detail={"error": {"code": e.code, "message": e.message}},
            ) from e
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": e.code, "message": e.message}},
        ) from e

    # Generate IDs
    doc_id = _generate_id()
    now = _now()

    # Identify format
    try:
        fmt = identify_format(magic, ext)
    except ValueError as e:
        raise HTTPException(
            status_code=415,
            detail={"error": {"code": "DOC_FORMAT_UNSUPPORTED", "message": f"Cannot identify format for '{ext}'."}},
        ) from e

    # Determine storage path
    storage_path = f"projects/{project_id}/{doc_id}/{filename}"

    # Store in MinIO
    try:
        upload_file(file_bytes, storage_path, content_type=file.content_type or "application/octet-stream")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "DOC_MINIO_ERROR", "message": f"Failed to store file: {e}"}},
        ) from e

    # Create document record (DB or in-memory fallback)
    title = custom_meta.get("title") if custom_meta else None
    async with _get_session() as session:
        await db.insert_document(
            session,
            doc_id=doc_id,
            project_id=project_id,
            filename=storage_path,
            original_name=filename,
            fmt=fmt.value,
            size_bytes=len(file_bytes),
            storage_path=storage_path,
            is_internal=is_internal,
            title=title,
        )

    # Trigger async processing in background (runs DB updates in its own session)
    asyncio.create_task(
        _execute_processing_pipeline_async(
            document_id=doc_id,
            project_id=project_id,
            filename=filename,
            storage_path=storage_path,
            is_internal=is_internal,
            custom_metadata=custom_meta,
            file_bytes=file_bytes,
            extension=ext,
        )
    )

    return DocumentUploadResponse(
        document_id=doc_id,
        filename=filename,
        format=fmt.value,
        size_bytes=len(file_bytes),
        parse_status="pending",
        created_at=now,
    )


async def _reindex_worker(
    *,
    document_id: str,
    project_id: str,
    filename: str,
    storage_path: str,
    is_internal: bool,
    custom_metadata: dict[str, Any],
    extension: str,
) -> None:
    """Background worker for reindex: download from MinIO then process.

    Runs as an async background task with its own DB session.
    """
    logger.info("Reindex worker started for %s", document_id)
    async with _get_session() as session:
        try:
            file_bytes = None
            if storage_path:
                try:
                    from document_service.minio_client import download_file as minio_download
                    loop = asyncio.get_running_loop()
                    file_bytes = await loop.run_in_executor(None, minio_download, storage_path)
                except Exception as e:
                    logger.warning("Could not download from MinIO for reindex: %s", e)

            if file_bytes is None:
                await db.update_document_status(
                    session, document_id, "error",
                    parse_error="Original file not found in MinIO for reindex",
                )
                logger.error("Reindex failed for %s: original file not found", document_id)
                return

            await _execute_processing_pipeline_async(
                document_id=document_id,
                project_id=project_id,
                filename=filename,
                storage_path=storage_path,
                is_internal=is_internal,
                custom_metadata=custom_metadata,
                file_bytes=file_bytes,
                extension=extension,
            )
            logger.info("Reindex worker complete for %s", document_id)
        except Exception as e:
            await db.update_document_status(
                session, document_id, "error",
                parse_error=str(e),
            )
            logger.error("Reindex worker failed for %s: %s", document_id, e)


async def _execute_processing_pipeline_async(
    *,
    document_id: str,
    project_id: str,
    filename: str,
    storage_path: str,
    is_internal: bool,
    custom_metadata: dict[str, Any],
    file_bytes: bytes,
    extension: str,
) -> None:
    """Execute the processing pipeline with async DB access.

    CPU-bound parsing/chunking runs in the default executor pool;
    all DB operations use the async session directly.
    """
    logger.info("Processing pipeline started for %s", document_id)

    # Update status to parsing (own session)
    async with _get_session() as session:
        await db.update_document_status(session, document_id, "parsing")

    try:
        # Parse document (CPU-bound → executor)
        loop = asyncio.get_running_loop()
        content = await loop.run_in_executor(None, parse_document, file_bytes, filename, extension)

        # Extract metadata (CPU-bound → executor)
        doc_metadata = await loop.run_in_executor(
            None, extract_metadata, content, file_bytes, filename, custom_metadata
        )

        # Generate chunks (CPU-bound → executor)
        from document_service.chunker.chunk_metadata import generate_chunks
        chunk_records = await loop.run_in_executor(
            None, generate_chunks, content, document_id, project_id
        )

        # Store chunks and update document in DB
        async with _get_session() as session:
            chunk_dicts = [
                {
                    "id": c.chunk_id,
                    "document_id": c.document_id,
                    "project_id": c.project_id,
                    "chunk_text": c.chunk_text,
                    "chunk_index": c.chunk_index,
                    "token_count": c.token_count,
                    "chunk_type": c.chunk_type,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "section_title": c.section_title,
                    "paragraph_index": c.paragraph_index,
                    "created_at": c.created_at.isoformat() if hasattr(c.created_at, "isoformat") else str(c.created_at),
                }
                for c in chunk_records
            ]
            # Delete old chunks first (in case of reindex), then insert new ones
            await db.delete_chunks(session, document_id)
            await db.insert_chunks(session, chunk_dicts)

            await db.update_document_status(
                session,
                document_id,
                "ready",
                page_count=doc_metadata.page_count,
                title=doc_metadata.model_dump().get("title"),
                author=", ".join(doc_metadata.authors) or None,
            )

        # Index chunks in KB service
        await _index_chunks_in_kb_service(document_id, project_id, chunk_records)

        logger.info("Processing pipeline complete for %s", document_id)

    except Exception as e:
        async with _get_session() as session:
            await db.update_document_status(
                session, document_id, "error",
                parse_error=str(e),
            )
        logger.error("Processing failed for %s: %s", document_id, e)


# Legacy sync wrapper removed; callers now use async version directly.


# ---------------------------------------------------------------------------
# M2-33: List documents
# ---------------------------------------------------------------------------


@app.get("/api/projects/{project_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    project_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    status: str | None = Query(default=None),
    format: str | None = Query(default=None),
) -> DocumentListResponse:
    """List documents for a project with pagination and optional filters."""
    async with _get_session() as session:
        items, total = await db.list_project_documents(
            session,
            project_id,
            status=status,
            doc_format=format,
            page=page,
            page_size=page_size,
        )

    result_items = [
        DocumentListItem(
            document_id=doc["id"],
            original_name=doc["original_name"],
            format=doc["format"],
            size_bytes=doc["size_bytes"],
            page_count=doc.get("page_count", 0),
            parse_status=doc["parse_status"],
            metadata=doc.get("metadata", {}),
            is_internal=doc.get("is_internal", False),
            chunk_count=doc.get("chunk_count", 0),
            created_at=doc["created_at"],
        )
        for doc in items
    ]

    pages_count = (total + page_size - 1) // page_size if total > 0 else 1

    return DocumentListResponse(
        items=result_items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages_count,
    )


# ---------------------------------------------------------------------------
# M2-34: Document detail
# ---------------------------------------------------------------------------


@app.get(
    "/api/projects/{project_id}/documents/{document_id}",
    response_model=DocumentDetailResponse,
    responses={404: {"description": "Document not found"}},
)
async def get_document_endpoint(project_id: str, document_id: str) -> DocumentDetailResponse:
    """Get full document detail including parse status and storage path."""
    async with _get_session() as session:
        doc = await db.get_document(session, document_id)
    if doc is None or str(doc.get("project_id", "")) != project_id:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "DOC_NOT_FOUND", "message": f"Document '{document_id}' not found."}},
        )

    return DocumentDetailResponse(
        document_id=doc["id"],
        project_id=doc["project_id"],
        original_name=doc["original_name"],
        format=doc["format"],
        size_bytes=doc["size_bytes"],
        page_count=doc.get("page_count", 0),
        parse_status=doc["parse_status"],
        metadata=doc.get("metadata", {}),
        is_internal=doc.get("is_internal", False),
        storage_path=doc.get("storage_path", "") or "",
        parse_error=doc.get("parse_error"),
        chunk_count=doc.get("chunk_count", 0),
        created_at=doc["created_at"],
        updated_at=doc.get("updated_at"),
    )


# ---------------------------------------------------------------------------
# M2-35: Delete document
# ---------------------------------------------------------------------------


@app.delete(
    "/api/projects/{project_id}/documents/{document_id}",
    status_code=204,
    responses={404: {"description": "Document not found"}},
)
async def delete_document(project_id: str, document_id: str) -> None:
    """Delete a document and cascade: MinIO file + chunks + vectors."""
    async with _get_session() as session:
        doc = await db.get_document(session, document_id)
        if doc is None or str(doc.get("project_id", "")) != project_id:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "DOC_NOT_FOUND", "message": f"Document '{document_id}' not found."}},
            )

    storage_path = doc.get("storage_path", "")
    if storage_path:
        try:
            minio_delete_file(str(storage_path))
        except Exception as e:
            logger.warning("Failed to delete MinIO object: %s", e)

    # Remove document + chunks from DB (cascade)
    async with _get_session() as session:
        await db.delete_document_db(session, document_id)

    logger.info("Document %s deleted (cascade)", document_id)


# ---------------------------------------------------------------------------
# M2-36: Reindex document
# ---------------------------------------------------------------------------


@app.post(
    "/api/projects/{project_id}/documents/{document_id}/reindex",
    response_model=ReindexResponse,
    responses={404: {"description": "Document not found"}, 409: {"description": "Document still processing"}},
)
async def reindex_document(project_id: str, document_id: str) -> ReindexResponse:
    """Re-trigger parsing and indexing for a document.

    Useful after chunk parameter adjustments.
    Only valid for documents in 'ready' or 'error' status.
    """
    async with _get_session() as session:
        doc = await db.get_document(session, document_id)
        if doc is None or str(doc.get("project_id", "")) != project_id:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "DOC_NOT_FOUND", "message": f"Document '{document_id}' not found."}},
            )

        current_status = doc["parse_status"]
        if current_status in ("pending", "parsing"):
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "DOC_STILL_PROCESSING",
                        "message": f"Document is currently '{current_status}'. Cannot reindex.",
                    }
                },
            )

        # Reset to parsing
        await db.update_document_status(session, document_id, "parsing")

    # Dispatch reindex to background
    storage_path = doc.get("storage_path", "") or ""
    ext = os.path.splitext(doc.get("original_name", ""))[1].lower()
    custom_metadata = doc.get("metadata", {})
    is_internal = doc.get("is_internal", False)

    asyncio.create_task(
        _reindex_worker(
            document_id=document_id,
            project_id=project_id,
            filename=doc.get("original_name", ""),
            storage_path=str(storage_path),
            is_internal=bool(is_internal),
            custom_metadata=custom_metadata if isinstance(custom_metadata, dict) else {},
            extension=ext,
        )
    )

    return ReindexResponse(
        document_id=document_id,
        parse_status="parsing",
        message="Reindex triggered successfully.",
    )


# ---------------------------------------------------------------------------
# Document content retrieval
# ---------------------------------------------------------------------------


@app.get(
    "/api/projects/{project_id}/documents/{document_id}/content",
    response_model=dict,
    responses={404: {"description": "Document not found"}, 409: {"description": "Document not parsed yet"}},
)
async def get_document_content(project_id: str, document_id: str) -> dict:
    """Get the full text content of a parsed document.

    Assembles all chunks into a single text output, organized by page/section.
    For image files without text chunks, returns an image indicator.
    """
    async with _get_session() as session:
        doc = await db.get_document(session, document_id)
        if doc is None or str(doc.get("project_id", "")) != project_id:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "DOC_NOT_FOUND", "message": f"Document '{document_id}' not found."}},
            )

        if doc["parse_status"] != "ready":
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "DOC_NOT_READY",
                        "message": f"Document is '{doc['parse_status']}', not ready for content viewing.",
                    }
                },
            )

        chunks = await db.get_chunks(session, document_id)
    if not chunks:
        # Image files may have no text chunks
        image_formats = {"png", "jpg", "jpeg", "tiff", "bmp", "gif", "webp"}
        if doc.get("format", "").lower() in image_formats:
            return {
                "document_id": document_id,
                "original_name": doc["original_name"],
                "format": doc["format"],
                "content_type": "image",
                "text": "",
            }
        return {
            "document_id": document_id,
            "original_name": doc["original_name"],
            "format": doc["format"],
            "content_type": "text",
            "text": "",
        }

    # Sort chunks by chunk_index and assemble text
    sorted_chunks = sorted(chunks, key=lambda c: c.get("chunk_index", 0))
    lines: list[str] = []
    current_section = None

    for c in sorted_chunks:
        section = c.get("section_title", "")
        if section and section != current_section:
            current_section = section
            lines.append(f"\n## {section}\n")

        page_start = c.get("page_start", 0)
        page_end = c.get("page_end", 0)
        if page_start or page_end:
            lines.append(f"[p{page_start}-{page_end}] {c.get('chunk_text', '')}")
        else:
            lines.append(c.get("chunk_text", ""))

    return {
        "document_id": document_id,
        "original_name": doc["original_name"],
        "format": doc["format"],
        "content_type": "text",
        "text": "\n".join(lines),
        "page_count": doc.get("page_count", 0),
        "chunk_count": len(sorted_chunks),
    }


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(FileValidationError)
async def file_validation_handler(request: Any, exc: FileValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(DocFormatUnsupportedError)
async def format_unsupported_handler(request: Any, exc: DocFormatUnsupportedError) -> JSONResponse:
    return JSONResponse(
        status_code=415,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(DocumentNotFoundError)
async def not_found_handler(request: Any, exc: DocumentNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(ParseError)
async def parse_error_handler(request: Any, exc: ParseError) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


# ---------------------------------------------------------------------------
# Helper to clear state (for testing)
# ---------------------------------------------------------------------------


def _reset_state() -> None:
    """Clear all state (for testing). Resets MinIO client and in-memory store."""
    reset_minio_client()
    # Clear in-memory store (only affects in-memory fallback, not real DB)
    db.reset_in_memory_store()
