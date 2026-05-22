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

import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from document_service.config import config
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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="EconAI Document Service",
    version="0.1.0",
    description="Document upload, parsing, chunking, and management (M2).",
)

# ---------------------------------------------------------------------------
# In-memory document store (MVP, no PostgreSQL dependency for development/test)
# ---------------------------------------------------------------------------

_documents: dict[str, dict[str, Any]] = {}
_chunks: dict[str, list[dict[str, Any]]] = {}

# ---------------------------------------------------------------------------
# Mock Redis client for pub/sub (MVP; replace with real Redis in production)
# ---------------------------------------------------------------------------


class MockRedis:
    """Mock Redis for development/testing."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1

    def get_published(self) -> list[tuple[str, str]]:
        return self.published


_mock_redis = MockRedis()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _generate_id() -> str:
    return str(uuid.uuid4())


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

    # Create document record (in-memory for MVP)
    doc_record = {
        "id": doc_id,
        "project_id": project_id,
        "filename": storage_path,
        "original_name": filename,
        "format": fmt.value,
        "size_bytes": len(file_bytes),
        "storage_path": storage_path,
        "parse_status": "pending",
        "page_count": 0,
        "metadata": custom_meta,
        "is_internal": is_internal,
        "parse_error": None,
        "created_at": now,
        "updated_at": now,
    }
    _documents[doc_id] = doc_record

    # Trigger async processing (run synchronously for MVP)
    try:
        # In production this would be: process_document.delay(doc_id, project_id, filename, storage_path, ...)
        # For MVP/test, we execute synchronously
        _execute_processing_pipeline(
            document_id=doc_id,
            project_id=project_id,
            filename=filename,
            storage_path=storage_path,
            is_internal=is_internal,
            custom_metadata=custom_meta,
            file_bytes=file_bytes,
            extension=ext,
        )
    except Exception as e:
        logger.error("Processing pipeline failed for %s: %s", doc_id, e)

    return DocumentUploadResponse(
        document_id=doc_id,
        filename=filename,
        format=fmt.value,
        size_bytes=len(file_bytes),
        parse_status="pending",
        created_at=now,
    )


def _execute_processing_pipeline(
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
    """Execute the processing pipeline synchronously (MVP/development mode)."""

    # Update status to parsing
    _documents[document_id]["parse_status"] = "parsing"
    _documents[document_id]["updated_at"] = _now()

    try:
        # Parse document
        content = parse_document(file_bytes, filename, extension)

        # Extract metadata
        doc_metadata = extract_metadata(content, file_bytes, filename, custom_metadata)

        # Generate chunks
        from document_service.chunker.chunk_metadata import generate_chunks
        chunk_records = generate_chunks(content, document_id, project_id)

        # Store chunks in memory
        _chunks[document_id] = [
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

        # Update document record
        _documents[document_id].update({
            "parse_status": "ready",
            "page_count": doc_metadata.page_count,
            "metadata": doc_metadata.model_dump(),
            "updated_at": _now(),
        })

        # Publish index event
        from document_service.models import IndexEvent
        event = IndexEvent(
            document_id=document_id,
            project_id=project_id,
            chunk_ids=[c.chunk_id for c in chunk_records],
            is_internal=is_internal,
        )
        _mock_redis.publish("kb:index:request", event.model_dump_json())

    except Exception as e:
        _documents[document_id].update({
            "parse_status": "error",
            "parse_error": str(e),
            "updated_at": _now(),
        })
        logger.error("Processing failed for %s: %s", document_id, e)


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
    # Filter by project
    items = [
        doc for doc in _documents.values()
        if doc["project_id"] == project_id
    ]

    # Apply filters
    if status:
        items = [doc for doc in items if doc["parse_status"] == status]
    if format:
        items = [doc for doc in items if doc["format"] == format]

    # Sort by created_at desc
    items.sort(key=lambda d: d["created_at"], reverse=True)

    total = len(items)

    # Paginate
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    # Build response
    result_items = []
    for doc in page_items:
        chunk_count = len(_chunks.get(doc["id"], []))
        result_items.append(DocumentListItem(
            document_id=doc["id"],
            original_name=doc["original_name"],
            format=doc["format"],
            size_bytes=doc["size_bytes"],
            page_count=doc.get("page_count", 0),
            parse_status=doc["parse_status"],
            metadata=doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {},
            is_internal=doc.get("is_internal", False),
            chunk_count=chunk_count,
            created_at=doc["created_at"],
        ))

    pages = (total + page_size - 1) // page_size if total > 0 else 1

    return DocumentListResponse(
        items=result_items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


# ---------------------------------------------------------------------------
# M2-34: Document detail
# ---------------------------------------------------------------------------


@app.get(
    "/api/projects/{project_id}/documents/{document_id}",
    response_model=DocumentDetailResponse,
    responses={404: {"description": "Document not found"}},
)
async def get_document(project_id: str, document_id: str) -> DocumentDetailResponse:
    """Get full document detail including parse status and storage path."""
    doc = _documents.get(document_id)
    if doc is None or doc["project_id"] != project_id:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "DOC_NOT_FOUND", "message": f"Document '{document_id}' not found."}},
        )

    chunk_count = len(_chunks.get(document_id, []))

    return DocumentDetailResponse(
        document_id=doc["id"],
        project_id=doc["project_id"],
        original_name=doc["original_name"],
        format=doc["format"],
        size_bytes=doc["size_bytes"],
        page_count=doc.get("page_count", 0),
        parse_status=doc["parse_status"],
        metadata=doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {},
        is_internal=doc.get("is_internal", False),
        storage_path=doc.get("storage_path", ""),
        parse_error=doc.get("parse_error"),
        chunk_count=chunk_count,
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
    doc = _documents.get(document_id)
    if doc is None or doc["project_id"] != project_id:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "DOC_NOT_FOUND", "message": f"Document '{document_id}' not found."}},
        )

    storage_path = doc.get("storage_path", "")
    if storage_path:
        try:
            minio_delete_file(storage_path)
        except Exception as e:
            logger.warning("Failed to delete MinIO object: %s", e)

    # Remove chunks
    _chunks.pop(document_id, None)

    # Remove document
    del _documents[document_id]

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
    doc = _documents.get(document_id)
    if doc is None or doc["project_id"] != project_id:
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
    doc["parse_status"] = "parsing"
    doc["updated_at"] = _now()

    # Re-download and reprocess
    storage_path = doc.get("storage_path", "")
    try:
        file_bytes = None
        if storage_path:
            try:
                from document_service.minio_client import download_file as minio_download
                file_bytes = minio_download(storage_path)
            except Exception as e:
                logger.warning("Could not download from MinIO for reindex: %s", e)

        if file_bytes is None:
            # Can't reprocess without file
            doc["parse_status"] = "error"
            doc["parse_error"] = "Original file not found in MinIO for reindex"
            doc["updated_at"] = _now()
            raise HTTPException(
                status_code=500,
                detail={"error": {"code": "DOC_REINDEX_NO_FILE", "message": "Original file not found for reindex."}},
            )

        ext = os.path.splitext(doc["original_name"])[1].lower()

        _execute_processing_pipeline(
            document_id=document_id,
            project_id=project_id,
            filename=doc["original_name"],
            storage_path=storage_path,
            is_internal=doc.get("is_internal", False),
            custom_metadata=doc.get("metadata", {}),
            file_bytes=file_bytes,
            extension=ext,
        )

    except HTTPException:
        raise
    except Exception as e:
        doc["parse_status"] = "error"
        doc["parse_error"] = str(e)
        doc["updated_at"] = _now()
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "DOC_REINDEX_FAILED", "message": f"Reindex failed: {e}"}},
        ) from e

    return ReindexResponse(
        document_id=document_id,
        parse_status=doc["parse_status"],
        message="Reindex triggered successfully.",
    )


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
    """Clear all in-memory state (for testing)."""
    _documents.clear()
    _chunks.clear()
    _mock_redis.published.clear()
    reset_minio_client()


def _get_mock_redis() -> MockRedis:
    """Get the mock Redis instance (for testing)."""
    return _mock_redis
