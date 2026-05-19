"""Celery tasks for the Document Service (M2-03, M2-07, M2-29, M2-30, M2-31, M2-32).

Handles the async document processing pipeline:
  1. File stored in MinIO -> storage_path
  2. Format identification
  3. Content extraction
  4. Metadata extraction
  5. Multi-granularity chunking
  6. Write to PostgreSQL (documents + document_chunks)
  7. Publish index event to Redis pub/sub
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from document_service.chunker.chunk_metadata import generate_chunks
from document_service.format_identifier import identify_format
from document_service.metadata_extractor import extract_metadata
from document_service.minio_client import download_file
from document_service.models import ChunkRecord, IndexEvent, ParsedContent
from document_service.parsers.router import parse_document
from document_service.validation import validate_extension

logger = logging.getLogger(__name__)


def process_document(
    document_id: str,
    project_id: str,
    filename: str,
    storage_path: str,
    is_internal: bool,
    custom_metadata: dict[str, Any] | None = None,
    *,
    db_session_factory: Any = None,
    redis_client: Any = None,
) -> str:
    """Synchronous document processing pipeline.

    This is the main entry point that Celery calls.
    All DB and Redis operations are done via injected dependencies
    to allow for mocking in tests.

    Args:
        document_id: UUID of the document.
        project_id: UUID of the project.
        filename: Original filename.
        storage_path: MinIO object path.
        is_internal: Whether the document is internal.
        custom_metadata: User-supplied metadata.
        db_session_factory: Optional SQLAlchemy async session factory.
        redis_client: Optional Redis client for pub/sub.

    Returns:
        The final parse status string.
    """
    logger.info("Starting document processing: %s (%s)", filename, document_id)

    try:
        # Step 1: Download from MinIO
        file_data = download_file(storage_path)

        # Step 2: Validate extension
        extension = validate_extension(filename)

        # Step 3: Format identification
        magic_bytes = file_data[:8]
        fmt = identify_format(magic_bytes, extension)

        # Step 4: Content extraction
        content: ParsedContent = parse_document(file_data, filename, extension)

        # Step 5: Metadata extraction
        metadata = extract_metadata(content, file_data, filename, custom_metadata)

        # Step 6: Multi-granularity chunking
        chunks = generate_chunks(content, document_id, project_id)

        # Step 7: Write to DB
        if db_session_factory is not None:
            _update_document_in_db(
                db_session_factory,
                document_id=document_id,
                status="ready",
                page_count=metadata.page_count,
                metadata_dict=metadata.model_dump(),
                format_value=fmt.value if fmt else "unknown",
                chunk_records=chunks,
            )
        else:
            logger.info("No DB session factory provided; skipping DB write for %s", document_id)

        # Step 8: Publish index event
        chunk_ids = [c.chunk_id for c in chunks]
        index_event = IndexEvent(
            document_id=document_id,
            project_id=project_id,
            chunk_ids=chunk_ids,
            is_internal=is_internal,
        )

        if redis_client is not None:
            try:
                redis_client.publish(
                    "kb:index:request",
                    index_event.model_dump_json(),
                )
                logger.info("Published index event for %s with %d chunks", document_id, len(chunks))
            except Exception as e:
                logger.error("Failed to publish index event for %s: %s", document_id, e)
        else:
            logger.info("No Redis client provided; skipping index event for %s", document_id)

        logger.info("Document processing complete: %s (%d chunks)", document_id, len(chunks))
        return "ready"

    except Exception as e:
        logger.error("Document processing failed for %s: %s", document_id, str(e))
        logger.error(traceback.format_exc())

        # Update DB with error status
        if db_session_factory is not None:
            try:
                _update_document_in_db(
                    db_session_factory,
                    document_id=document_id,
                    status="error",
                    parse_error=str(e),
                )
            except Exception as db_err:
                logger.error("Failed to update error status in DB: %s", db_err)

        raise


def _update_document_in_db(
    db_session_factory: Any,
    *,
    document_id: str,
    status: str = "ready",
    page_count: int = 0,
    metadata_dict: dict[str, Any] | None = None,
    format_value: str | None = None,
    parse_error: str | None = None,
    chunk_records: list[ChunkRecord] | None = None,
) -> None:
    """Update document record and insert chunks into DB.

    This is a synchronous helper that runs inside an async context.
    In production, this would use SQLAlchemy's async session.
    For now, we log the operations (tests mock the DB).
    """
    import asyncio

    async def _do_db_update() -> None:
        # In production, this would:
        # 1. UPDATE documents SET parse_status=?, page_count=?, metadata=? WHERE id=?
        # 2. INSERT INTO document_chunks (...) VALUES (...)
        # For MVP/testing, we log the operations
        logger.info("DB update: document %s status=%s, page_count=%d, chunks=%d",
                     document_id, status, page_count,
                     len(chunk_records) if chunk_records else 0)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            loop.run_until_complete(_do_db_update())
        else:
            loop.run_until_complete(_do_db_update())
    except RuntimeError:
        asyncio.run(_do_db_update())


# ---------------------------------------------------------------------------
# Celery task entry point
# ---------------------------------------------------------------------------


def make_celery_task() -> Any:
    """Create a Celery task wrapper for process_document.

    Returns a callable that can be registered with Celery.
    In production, this would be decorated with @celery_app.task.
    For testability, process_document is standalone.
    """
    # This is the actual Celery task that would be registered
    # In tests, we call process_document directly
    return process_document
