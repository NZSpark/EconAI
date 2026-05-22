"""Configuration management for the Output Generation Service (M7-02)."""

from pydantic_settings import BaseSettings


class OutputServiceConfig(BaseSettings):
    """Configuration for the Output Generation Service."""

    # Service identity
    SERVICE_NAME: str = "output-service"
    SERVICE_PORT: int = 8006

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "econai-outputs"
    MINIO_SECURE: bool = False

    # Output storage
    OUTPUT_STORAGE_PATH: str = "outputs/"
    OUTPUT_TEMPLATES_DIR: str = "templates/output/"
    OUTPUT_MAX_FILE_SIZE_MB: int = 50

    # DOCX
    DOCX_INSTITUTION_NAME: str = "EconAI 分析中心"
    DOCX_DEFAULT_FONT: str = "仿宋_GB2312"

    # PPTX
    PPTX_DEFAULT_THEME: str = "default"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://econai:econai_secret_change_me@localhost:5432/econai"

    model_config = {"case_sensitive": True}


config = OutputServiceConfig()
