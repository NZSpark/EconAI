"""Celery worker configuration for the Document Service (M2-03).

Registers the 'document' queue for document processing tasks.
"""

from __future__ import annotations

from typing import Any

from document_service.config import config


def create_celery_app() -> Any:
    """Create and configure the Celery application.

    Returns a Celery app instance configured with:
      - Redis broker
      - Redis result backend
      - 'document' queue
      - JSON serialization
    """
    from celery import Celery

    app = Celery(
        "document_service",
        broker=config.CELERY_BROKER_URL,
        backend=config.CELERY_RESULT_BACKEND,
    )

    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_default_queue=config.CELERY_DOCUMENT_QUEUE,
        task_queues={
            config.CELERY_DOCUMENT_QUEUE: {
                "exchange": config.CELERY_DOCUMENT_QUEUE,
                "routing_key": config.CELERY_DOCUMENT_QUEUE,
            },
        },
        task_routes={
            "document_service.tasks.*": {"queue": config.CELERY_DOCUMENT_QUEUE},
        },
    )

    return app


# Create the Celery app instance for workers
celery_app = create_celery_app()


# Register the document processing task
@celery_app.task(bind=True, max_retries=0, name="process_document")  # type: ignore[untyped-decorator]
def process_document_task(
    self: Any,
    document_id: str,
    project_id: str,
    filename: str,
    storage_path: str,
    is_internal: bool = False,
    custom_metadata: dict[str, Any] | None = None,
) -> str:
    """Celery task wrapper for document processing.

    This can be called as: process_document_task.delay(doc_id, proj_id, ...)
    """
    from document_service.tasks import process_document
    return process_document(
        document_id=document_id,
        project_id=project_id,
        filename=filename,
        storage_path=storage_path,
        is_internal=is_internal,
        custom_metadata=custom_metadata,
    )
