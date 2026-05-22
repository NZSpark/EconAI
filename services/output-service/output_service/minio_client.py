"""MinIO output storage client — delegates to shared.minio_client for output service."""

from __future__ import annotations

import logging

from shared.minio_client import MinIOClient, MinIOConfig

from output_service.config import config

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
    """Get the output-service MinIO client."""
    return _client


def reset_minio_client() -> None:
    """Reset the client singleton (for testing)."""
    _client.reset()


def upload_file(file_data: bytes, object_path: str, content_type: str = "application/octet-stream") -> str:
    """Upload file bytes to MinIO. Returns the object_path."""
    return _client.upload_file(file_data, object_path, content_type)


def download_file(object_path: str) -> bytes:
    """Download file bytes from MinIO."""
    return _client.download_file(object_path)


def get_presigned_url(object_path: str, expires: int = 3600) -> str:
    """Generate a presigned URL for temporary access."""
    return _client.get_presigned_url(object_path, expires)


def generate_output_path(task_id: str, format_name: str) -> str:
    """Generate a deterministic storage path for an output file."""
    prefix = config.OUTPUT_STORAGE_PATH.rstrip("/")
    ext_map = {"md": "md", "markdown": "md", "docx": "docx", "xlsx": "xlsx", "pptx": "pptx"}
    ext = ext_map.get(format_name, format_name)
    return f"{prefix}/task-{task_id}/output.{ext}"
