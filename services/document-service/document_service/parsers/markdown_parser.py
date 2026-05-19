"""Markdown and plain text parser (M2-12).

Preserves heading hierarchy structure.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from document_service.models import PageContent, ParsedContent, SectionInfo
from document_service.parsers.base import BaseParser

logger = logging.getLogger(__name__)

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


class MarkdownParser(BaseParser):
    """Parse Markdown and plain text files."""

    def supported_format(self) -> str:
        return "markdown"

    def parse(self, file_data: bytes, filename: str) -> ParsedContent:
        try:
            text = file_data.decode("utf-8")
        except UnicodeDecodeError:
            text = file_data.decode("latin-1", errors="replace")

        sections: list[SectionInfo] = []
        char_offset = 0
        for line in text.split("\n"):
            m = HEADING_PATTERN.match(line)
            if m:
                level = len(m.group(1))
                title = m.group(2).strip()
                sections.append(SectionInfo(
                    title=title,
                    level=level,
                    page_start=0,
                    start_char=char_offset,
                ))
            char_offset += len(line) + 1

        return ParsedContent(
            full_text=text,
            pages=[PageContent(page_number=1, text=text, has_text_layer=True)],
            tables=[],
            sections=sections,
            metadata_hints=self.extract_metadata_hints(file_data, filename),
            needs_ocr=False,
        )

    def extract_metadata_hints(self, file_data: bytes, filename: str) -> dict[str, Any]:
        """Extract hints from Markdown front matter if present."""
        try:
            text = file_data.decode("utf-8")
        except UnicodeDecodeError:
            text = file_data.decode("latin-1", errors="replace")

        hints: dict[str, Any] = {}

        # Simple YAML front matter detection
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                front_matter = parts[1].strip()
                for line in front_matter.split("\n"):
                    if ":" in line:
                        key, _, value = line.partition(":")
                        hints[key.strip()] = value.strip()
        return hints
