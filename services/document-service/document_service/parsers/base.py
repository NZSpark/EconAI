"""Base parser interface for all document format parsers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from document_service.models import ParsedContent


class BaseParser(ABC):
    """Abstract base for all document format parsers."""

    @abstractmethod
    def parse(self, file_data: bytes, filename: str) -> ParsedContent:
        """解析 file bytes and return structured content.

        Args:
            file_data: Raw file bytes.
            filename: Original filename (for context).

        Returns:
            ParsedContent with full_text, pages, tables, sections, metadata_hints.
        """
        ...

    @abstractmethod
    def supported_format(self) -> str:
        """Return the DocumentFormat string this parser handles."""
        ...

    def extract_metadata_hints(self, file_data: bytes, filename: str) -> dict[str, Any]:
        """提取 hints for metadata extraction. Override in subclasses."""
        return {}
