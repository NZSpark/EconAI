"""共享 MinIO 客户端 — 文档和输出服务使用的可配置包装器。

提供基于参数的工厂函数，使每个服务可以传入自己的 MinIO 连接设置。
避免了之前两个服务中约 200 行的重复代码。
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
    """MinIO 存储桶的连接参数。"""

    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    secure: bool = False


class MinIOClient:
    """封装单个存储桶的 MinIO 操作。

    通过延迟创建的单例实例实现线程安全。
    """

    def __init__(self, cfg: MinIOConfig) -> None:
        self._cfg = cfg
        self._client: Minio | None = None

    @property
    def client(self) -> Minio:
        """延迟创建并缓存 Minio 连接。"""
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
        """重置缓存的客户端（用于测试）。"""
        self._client = None

    def _ensure_bucket(self) -> None:
        """确保配置的存储桶存在，必要时创建。"""
        try:
            found = self.client.bucket_exists(self._cfg.bucket)
            if not found:
                self.client.make_bucket(self._cfg.bucket)
                logger.info("Created MinIO bucket: %s", self._cfg.bucket)
        except S3Error as e:
            logger.error("Failed to check/create MinIO bucket %s: %s", self._cfg.bucket, e)
            raise

    # ---- 核心操作 ----

    def upload_file(
        self, file_data: bytes, object_path: str, content_type: str = "application/octet-stream"
    ) -> str:
        """将文件字节上传到 MinIO。返回 object_path。"""
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
        """从 MinIO 下载文件字节。"""
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
        """从 MinIO 删除对象（幂等 — 如果未找到则记录警告）。"""
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
        """生成用于临时访问的预签名 URL。"""
        try:
            return self.client.presigned_get_object(  # type: ignore[no-any-return]
                bucket_name=self._cfg.bucket,
                object_name=object_path,
                expires=timedelta(seconds=expires),
            )
        except S3Error as e:
            logger.error("Failed to generate presigned URL: %s", e)
            raise
