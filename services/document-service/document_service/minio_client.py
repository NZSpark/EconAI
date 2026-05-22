"""MinIO storage client wrapper — delegates to shared.minio_client for document service."""

from __future__ import annotations

import logging

from minio.error import S3Error
from shared.minio_client import MinIOClient, MinIOConfig

from document_service.config import config
from document_service.errors import MinIOError as _MinIOError

logger = logging.getLogger(__name__)

_cfg = MinIOConfig(
    endpoint=config.MINIO_ENDPOINT,
    access_key=config.MINIO_ACCESS_KEY,
    secret_key=config.MINIO_SECRET_KEY,
    bucket=config.MINIO_BUCKET,
    secure=config.MINIO_SECURE,
)
_client = MinIOClient(_cfg)


def get_minio_client() -> MinIOClient:
    """Get the document-service MinIO client."""
    return _client


def reset_minio_client() -> None:
    """Reset the client singleton (useful for testing)."""
    _client.reset()


def upload_file(file_data: bytes, object_path: str, content_type: str = "application/octet-stream") -> str:
    """Upload file bytes to MinIO."""
    try:
        return _client.upload_file(file_data, object_path, content_type)
    except S3Error as e:
        raise _MinIOError("upload", str(e)) from e


def download_file(object_path: str) -> bytes:
    """Download file bytes from MinIO."""
    try:
        return _client.download_file(object_path)
    except S3Error as e:
        raise _MinIOError("download", str(e)) from e


def delete_file(object_path: str) -> None:
    """Delete an object from MinIO."""
    try:
        _client.delete_file(object_path)
    except S3Error as e:
        if "NoSuchKey" in str(e):
            logger.warning("Object not found in MinIO (already deleted?): %s", object_path)
        else:
            raise _MinIOError("delete", str(e)) from e
