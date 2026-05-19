"""MinIO storage client wrapper (M2-06).

Handles upload, download, delete operations with automatic bucket creation.
"""

from __future__ import annotations

import io
import logging

from minio import Minio
from minio.error import S3Error

from document_service.config import config
from document_service.errors import MinIOError

logger = logging.getLogger(__name__)

# Singleton client
_client: Minio | None = None


def get_minio_client() -> Minio:
    """Get or create a MinIO client singleton."""
    global _client
    if _client is None:
        _client = Minio(
            endpoint=config.MINIO_ENDPOINT,
            access_key=config.MINIO_ACCESS_KEY,
            secret_key=config.MINIO_SECRET_KEY,
            secure=config.MINIO_SECURE,
        )
        _ensure_bucket(_client)
    return _client


def reset_minio_client() -> None:
    """Reset the singleton client (useful for testing)."""
    global _client
    _client = None


def _ensure_bucket(client: Minio) -> None:
    """Ensure the configured bucket exists, creating it if needed."""
    try:
        found = client.bucket_exists(config.MINIO_BUCKET)
        if not found:
            client.make_bucket(config.MINIO_BUCKET)
            logger.info("Created MinIO bucket: %s", config.MINIO_BUCKET)
    except S3Error as e:
        raise MinIOError("bucket_check", str(e)) from e


def upload_file(file_data: bytes, object_path: str, content_type: str = "application/octet-stream") -> str:
    """Upload file bytes to MinIO.

    Args:
        file_data: Raw file bytes.
        object_path: Full object path in MinIO (e.g., "projects/{project_id}/{doc_id}/original.pdf").
        content_type: MIME content type of the file.

    Returns:
        The object_path that was written to.
    """
    client = get_minio_client()
    try:
        client.put_object(
            bucket_name=config.MINIO_BUCKET,
            object_name=object_path,
            data=io.BytesIO(file_data),
            length=len(file_data),
            content_type=content_type,
        )
        logger.info("Uploaded object to MinIO: %s", object_path)
        return object_path
    except S3Error as e:
        raise MinIOError("upload", str(e)) from e


def download_file(object_path: str) -> bytes:
    """Download file bytes from MinIO.

    Args:
        object_path: Full object path in MinIO.

    Returns:
        Raw file bytes.
    """
    client = get_minio_client()
    try:
        response = client.get_object(
            bucket_name=config.MINIO_BUCKET,
            object_name=object_path,
        )
        data = response.read()
        response.close()
        response.release_conn()
        return data
    except S3Error as e:
        raise MinIOError("download", str(e)) from e


def delete_file(object_path: str) -> None:
    """Delete an object from MinIO.

    Args:
        object_path: Full object path in MinIO.
    """
    client = get_minio_client()
    try:
        client.remove_object(
            bucket_name=config.MINIO_BUCKET,
            object_name=object_path,
        )
        logger.info("Deleted object from MinIO: %s", object_path)
    except S3Error as e:
        # Log but don't raise if the object doesn't exist (idempotent delete)
        if "NoSuchKey" in str(e):
            logger.warning("Object not found in MinIO (already deleted?): %s", object_path)
        else:
            raise MinIOError("delete", str(e)) from e
