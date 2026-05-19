"""Format router (M7-30).

Routes output generation requests to the appropriate generator based on format.
Supports parallel generation of multiple formats.
"""

from __future__ import annotations

from typing import Any

from output_service.docx_gen import DocxGenerator
from output_service.markdown_gen import MarkdownGenerator
from output_service.pptx_gen import PptxGenerator
from output_service.xlsx_gen import XlsxGenerator

CONTENT_TYPE_MAP = {
    "md": "text/markdown",
    "markdown": "text/markdown",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

EXTENSION_MAP = {
    "md": "md",
    "markdown": "md",
    "docx": "docx",
    "xlsx": "xlsx",
    "pptx": "pptx",
}


class FormatRouter:
    """Routes generation requests to the correct format handler."""

    def __init__(self) -> None:
        self._markdown = MarkdownGenerator()
        self._docx = DocxGenerator()
        self._xlsx = XlsxGenerator()
        self._pptx = PptxGenerator()

    def generate(
        self,
        format_name: str,
        title: str,
        sections: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> bytes:
        """Generate output for a single format.

        Args:
            format_name: One of "md", "markdown", "docx", "xlsx", "pptx".
            title: Document title.
            sections: Section data.
            citations: Citation data.
            metadata: Optional metadata.

        Returns:
            Generated file bytes.
        """
        if format_name in ("md", "markdown"):
            text = self._markdown.generate(title, sections, citations, metadata)
            return text.encode("utf-8")
        elif format_name == "docx":
            return self._docx.generate(title, sections, citations, metadata)
        elif format_name == "xlsx":
            return self._xlsx.generate(title, sections, citations, metadata)
        elif format_name == "pptx":
            return self._pptx.generate(title, sections, citations, metadata)
        else:
            raise ValueError(f"Unsupported output format: {format_name}")

    def generate_all(
        self,
        formats: list[str],
        title: str,
        sections: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate all requested formats.

        Returns a list of {"format": str, "data": bytes, "content_type": str, "extension": str} dicts.
        """
        results: list[dict[str, Any]] = []
        for fmt in formats:
            try:
                data = self.generate(fmt, title, sections, citations, metadata)
                results.append(
                    {
                        "format": fmt,
                        "data": data,
                        "content_type": CONTENT_TYPE_MAP.get(fmt, "application/octet-stream"),
                        "extension": EXTENSION_MAP.get(fmt, fmt),
                        "size_bytes": len(data),
                    }
                )
            except Exception as e:
                results.append({"format": fmt, "error": str(e)})
        return results
