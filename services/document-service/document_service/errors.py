"""文档服务错误处理（M2-37, M2-38）。"""

from __future__ import annotations

from typing import Any


class DocumentServiceError(Exception):
    """文档服务错误的基础异常。"""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class DocFormatUnsupportedError(DocumentServiceError):
    """M2-38：文档格式不受支持时抛出。"""

    def __init__(self, format_name: str, details: dict[str, Any] | None = None):
        super().__init__(
            "DOC_FORMAT_UNSUPPORTED",
            f"文档格式 '{format_name}' 不受支持。",
            details,
        )


class ParseError(DocumentServiceError):
    """M2-37：文档解析失败时抛出。"""

    def __init__(self, document_id: str, reason: str, details: dict[str, Any] | None = None):
        super().__init__(
            "DOC_PARSE_FAILED",
            f"解析文档 {document_id} 失败: {reason}",
            details,
        )


class MinIOError(DocumentServiceError):
    """MinIO 操作失败时抛出。"""

    def __init__(self, operation: str, reason: str, details: dict[str, Any] | None = None):
        super().__init__(
            "DOC_MINIO_ERROR",
            f"MinIO {operation} 失败: {reason}",
            details,
        )


class DocumentNotFoundError(DocumentServiceError):
    """文档未找到时抛出。"""

    def __init__(self, document_id: str):
        super().__init__(
            "DOC_NOT_FOUND",
            f"文档 '{document_id}' 未找到。",
        )
