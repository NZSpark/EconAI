"""Shared MinIO client — configurable wrapper used by document and output services.

Provides a parameter-based factory so each service passes its own MinIO connection
settings. Avoids the ~200 lines of duplicate code previously in two services.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MinIOConfig:
    """Connection parameters for a MinIO bucket."""

    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    secure: bool = False


class MinIOClient:
    """Encapsulates MinIO operations for a single bucket.

    Thread-safe via a lazily-created singleton instance.
    """

    def __init__(self, cfg: MinIOConfig) -> None:
        self._cfg = cfg
        self._client: Minio | None = None

    @property
    def client(self) -> Minio:
        """Lazily create and cache the Minio connection."""
        if self._client is None:
            self._client = Minio(
                endpoint=self._cfg.endpoint,
                access_key=self._cfg.access_key,
                secret_key=self._cfg.secret_key,
                secure=self._cfg.secure,
            )
            self._ensure_bucket()
        return self._client

    def reset(self) -> None:
        """Reset the cached client (useful for testing)."""
        self._client = None

    def _ensure_bucket(self) -> None:
        """Ensure the configured bucket exists, creating it if needed."""
        try:
            found = self.client.bucket_exists(self._cfg.bucket)
            if not found:
                self.client.make_bucket(self._cfg.bucket)
                logger.info("Created MinIO bucket: %s", self._cfg.bucket)
        except S3Error as e:
            logger.error("Failed to check/create MinIO bucket %s: %s", self._cfg.bucket, e)
            raise

    # ---- core operations ----

    def upload_file(
        self, file_data: bytes, object_path: str, content_type: str = "application/octet-stream"
    ) -> str:
        """Upload file bytes to MinIO. Returns the object_path."""
        try:
            self.client.put_object(
                bucket_name=self._cfg.bucket,
                object_name=object_path,
                data=io.BytesIO(file_data),
                length=len(file_data),
                content_type=content_type,
            )
            logger.info("Uploaded object to MinIO: %s", object_path)
            return object_path
        except S3Error as e:
            logger.error("Failed to upload to MinIO: %s", e)
            raise

    def download_file(self, object_path: str) -> bytes:
        """Download file bytes from MinIO."""
        try:
            response = self.client.get_object(
                bucket_name=self._cfg.bucket,
                object_name=object_path,
            )
            data = response.read()
            response.close()
            response.release_conn()
            return data  # type: ignore[no-any-return]
        except S3Error as e:
            logger.error("Failed to download from MinIO: %s", e)
            raise

    def delete_file(self, object_path: str) -> None:
        """Delete an object from MinIO (idempotent — logs warning if not found)."""
        try:
            self.client.remove_object(
                bucket_name=self._cfg.bucket,
                object_name=object_path,
            )
            logger.info("Deleted object from MinIO: %s", object_path)
        except S3Error as e:
            if "NoSuchKey" in str(e):
                logger.warning("Object not found in MinIO (already deleted?): %s", object_path)
            else:
                logger.error("Failed to delete from MinIO: %s", e)
                raise

    def get_presigned_url(self, object_path: str, expires: int = 3600) -> str:
        """Generate a presigned URL for temporary access."""
        try:
            return self.client.presigned_get_object(  # type: ignore[no-any-return]
                bucket_name=self._cfg.bucket,
                object_name=object_path,
                expires=timedelta(seconds=expires),
            )
        except S3Error as e:
            logger.error("Failed to generate presigned URL: %s", e)
            raise
