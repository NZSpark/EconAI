"""MinIO output storage client (M7-04).

Handles upload, download, presigned URL generation for generated output files.
"""

from __future__ import annotations

import io
import logging
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from output_service.config import config

logger = logging.getLogger(__name__)

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
    """Reset the singleton client (for testing)."""
    global _client
    _client = None


def _ensure_bucket(client: Minio) -> None:
    """Ensure the configured bucket exists."""
    try:
        if not client.bucket_exists(config.MINIO_BUCKET):
            client.make_bucket(config.MINIO_BUCKET)
            logger.info("Created MinIO bucket: %s", config.MINIO_BUCKET)
    except S3Error as e:
        logger.error("Failed to check/create MinIO bucket: %s", e)
        raise


def upload_file(file_data: bytes, object_path: str, content_type: str = "application/octet-stream") -> str:
    """Upload file bytes to MinIO. Returns the object_path."""
    client = get_minio_client()
    try:
        client.put_object(
            bucket_name=config.MINIO_BUCKET,
            object_name=object_path,
            data=io.BytesIO(file_data),
            length=len(file_data),
            content_type=content_type,
        )
        logger.info("Uploaded output to MinIO: %s", object_path)
        return object_path
    except S3Error as e:
        logger.error("Failed to upload to MinIO: %s", e)
        raise


def download_file(object_path: str) -> bytes:
    """Download file bytes from MinIO."""
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
        logger.error("Failed to download from MinIO: %s", e)
        raise


def get_presigned_url(object_path: str, expires: int = 3600) -> str:
    """Generate a presigned URL for temporary access."""
    client = get_minio_client()
    try:
        return client.presigned_get_object(
            bucket_name=config.MINIO_BUCKET,
            object_name=object_path,
            expires=timedelta(seconds=expires),
        )
    except S3Error as e:
        logger.error("Failed to generate presigned URL: %s", e)
        raise


def generate_output_path(task_id: str, format_name: str) -> str:
    """Generate a deterministic storage path for an output file."""
    prefix = config.OUTPUT_STORAGE_PATH.rstrip("/")
    ext_map = {"md": "md", "markdown": "md", "docx": "docx", "xlsx": "xlsx", "pptx": "pptx"}
    ext = ext_map.get(format_name, format_name)
    return f"{prefix}/task-{task_id}/output.{ext}"
