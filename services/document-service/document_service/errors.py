"""Error handling for Document Service (M2-37, M2-38)."""

from __future__ import annotations

from typing import Any


class DocumentServiceError(Exception):
    """Base exception for Document Service errors."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class DocFormatUnsupportedError(DocumentServiceError):
    """M2-38: Raised when a document format is not supported."""

    def __init__(self, format_name: str, details: dict[str, Any] | None = None):
        super().__init__(
            "DOC_FORMAT_UNSUPPORTED",
            f"Document format '{format_name}' is not supported.",
            details,
        )


class ParseError(DocumentServiceError):
    """M2-37: Raised when document parsing fails."""

    def __init__(self, document_id: str, reason: str, details: dict[str, Any] | None = None):
        super().__init__(
            "DOC_PARSE_FAILED",
            f"Failed to parse document {document_id}: {reason}",
            details,
        )


class MinIOError(DocumentServiceError):
    """Raised when MinIO operations fail."""

    def __init__(self, operation: str, reason: str, details: dict[str, Any] | None = None):
        super().__init__(
            "DOC_MINIO_ERROR",
            f"MinIO {operation} failed: {reason}",
            details,
        )


class DocumentNotFoundError(DocumentServiceError):
    """Raised when a document is not found."""

    def __init__(self, document_id: str):
        super().__init__(
            "DOC_NOT_FOUND",
            f"Document '{document_id}' not found.",
        )
