"""Configuration management for the Document Service (M2-02).

Configures: MinIO, chunk parameters, OCR language, file size limits, Celery queue.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class DocumentServiceConfig(BaseSettings):
    """Configuration for the Document Parsing Service."""

    # Service identity
    SERVICE_NAME: str = "document-service"
    SERVICE_PORT: int = 8001

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "econai-documents"
    MINIO_SECURE: bool = False

    # Chunk parameters - paragraph level
    CHUNK_PARAGRAPH_TARGET_TOKENS: int = 300
    CHUNK_PARAGRAPH_MIN_TOKENS: int = 100
    CHUNK_PARAGRAPH_MAX_TOKENS: int = 500
    CHUNK_PARAGRAPH_OVERLAP: int = 50

    # Chunk parameters - section level
    CHUNK_SECTION_TARGET_TOKENS: int = 2000
    CHUNK_SECTION_MIN_TOKENS: int = 500
    CHUNK_SECTION_MAX_TOKENS: int = 3000
    CHUNK_SECTION_OVERLAP: int = 100

    # OCR
    OCR_LANGUAGE: str = "chi_sim+eng"
    OCR_ENABLED: bool = True

    # File validation
    MAX_FILE_SIZE_MB: int = 100

    # Celery
    CELERY_DOCUMENT_QUEUE: str = "document"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://econai:econai_secret_change_me@localhost:5432/econai"

    # Redis for pub/sub
    REDIS_URL: str = "redis://localhost:6379/0"

    model_config = {"env_prefix": "DOCUMENT_", "case_sensitive": True}


@lru_cache
def get_config() -> DocumentServiceConfig:
    return DocumentServiceConfig()


# Singleton instance
config = get_config()
