"""EconAI shared package — common models, config loader, structured logging, and MinIO client."""

from shared.config import AppSettings, get_settings
from shared.log_setup import setup_logging
from shared.metrics import setup_metrics
from shared.minio_client import MinIOClient, MinIOConfig
from shared.models import (
    CitationConfidence,
    DocumentFormat,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    IndexEvent,
    Message,
    PaginatedResponse,
    PaginationParams,
    ParseStatus,
    TaskStatus,
    TaskType,
    UserRole,
)

__all__ = [
    "AppSettings",
    "CitationConfidence",
    "DocumentFormat",
    "ErrorDetail",
    "ErrorResponse",
    "HealthResponse",
    "IndexEvent",
    "Message",
    "MinIOClient",
    "MinIOConfig",
    "PaginatedResponse",
    "PaginationParams",
    "ParseStatus",
    "TaskStatus",
    "TaskType",
    "UserRole",
    "get_settings",
    "setup_logging",
    "setup_metrics",
]
