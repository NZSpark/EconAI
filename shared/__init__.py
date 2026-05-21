"""EconAI shared package — common models, config loader, and structured logging."""

from shared.config import AppSettings, get_settings
from shared.log_setup import setup_logging
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
    "PaginatedResponse",
    "PaginationParams",
    "ParseStatus",
    "TaskStatus",
    "TaskType",
    "UserRole",
    "get_settings",
    "setup_logging",
]
