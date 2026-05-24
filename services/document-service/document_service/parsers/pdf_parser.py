"""PDF parser using PyMuPDF (M2-10).

Extracts full text, page numbers, tables, embedded images (with OCR), and
image positions.
"""

from __future__ import annotations

import logging
from typing import Any

from document_service.models import PageContent, ParsedContent, SectionInfo
from document_service.parsers.base import BaseParser
from document_service.parsers.image_extractor import extract_images_from_pdf

logger = logging.getLogger(__name__)


class PDFParser(BaseParser):
    """Parse PDF files using PyMuPDF (fitz).

    Extracts: text (per-page), tables, section headers from TOC,
    and embedded images with OCR recognition.
    """

    def supported_format(self) -> str:
        return "pdf"

    def parse(self, file_data: bytes, filename: str) -> ParsedContent:
        """Extract text from PDF, per-page, with table and image detection."""
        try:
            import fitz  # PyMuPDF
        except ImportError as e:
            raise ImportError("PyMuPDF (fitz) is required for PDF parsing") from e

        doc = fitz.open(stream=file_data, filetype="pdf")
        pages: list[PageContent] = []
        sections: list[SectionInfo] = []
        all_tables: list[dict[str, Any]] = []
        full_text_parts: list[str] = []
        has_text_layer = False

        try:
            toc = doc.get_toc(simple=True)
            for level, title, page in toc:
                sections.append(SectionInfo(title=title, level=level, page_start=page))
        except Exception:
            logger.warning("Failed to extract PDF table of contents", exc_info=True)

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text()
            if page_text.strip():
                has_text_layer = True

            pages.append(PageContent(
                page_number=page_num + 1,
                text=page_text,
                has_text_layer=len(page_text.strip()) > 0,
            ))

            # Detect tables on this page
            try:
                tabs = page.find_tables()
                if tabs and tabs.tables:
                    for tab in tabs.tables:
                        table_data = {
                            "page": page_num + 1,
                            "rows": [[cell.to_dict().get("text", "") if hasattr(cell, "to_dict") else str(cell)
                                      for cell in row]
                                     for row in tab.extract()] if hasattr(tab, "extract") else [],
                        }
                        all_tables.append(table_data)
            except Exception:
                logger.warning(
                    "PDF table extraction failed on page %d of %s", page_num + 1, filename, exc_info=True
                )

            full_text_parts.append(page_text)

        doc.close()

        full_text = "\n\n".join(full_text_parts)

        # ---- Extract and OCR embedded images ----
        ocr_images = extract_images_from_pdf(file_data)

        # Append OCR text from images to the page they belong to
        image_text_by_page: dict[int, list[str]] = {}
        for img in ocr_images:
            page_num = img.get("page", 1)
            ocr_text = img.get("ocr_text", "")
            if ocr_text:
                image_text_by_page.setdefault(page_num, []).append(
                    f"[Image {img.get('image_index', 0)} OCR]: {ocr_text}"
                )

        # Merge image OCR text into corresponding pages
        for page_idx, page_content in enumerate(pages):
            pn = page_content.page_number
            if pn in image_text_by_page:
                extra_text = "\n\n".join(image_text_by_page[pn])
                page_content.text = (page_content.text + "\n\n" + extra_text).strip()
                # Update the full_text_parts entry too
                if page_idx < len(full_text_parts):
                    full_text_parts[page_idx] = page_content.text

        if image_text_by_page:
            full_text = "\n\n".join(full_text_parts)
        # ---- End image extraction ----

        # Map sections to character offsets
        for section in sections:
            section.start_char = 0  # We'll set this in chunker if needed

        return ParsedContent(
            full_text=full_text,
            pages=pages,
            tables=all_tables,
            sections=sections or _detect_sections_from_text(full_text),
            metadata_hints=self.extract_metadata_hints(file_data, filename),
            needs_ocr=not has_text_layer,
            ocr_images=ocr_images,
        )

    def extract_metadata_hints(self, file_data: bytes, filename: str) -> dict[str, Any]:
        """Extract PDF metadata hints."""
        try:
            import fitz
            doc = fitz.open(stream=file_data, filetype="pdf")
            meta = doc.metadata
            doc.close()
            return {
                "title": meta.get("title", ""),
                "author": meta.get("author", ""),
                "date": meta.get("creationDate", ""),
                "source": meta.get("producer", ""),
                "pdf_metadata": dict(meta),
            }
        except Exception:
            return {}


def _detect_sections_from_text(text: str) -> list[SectionInfo]:
    """Fallback: detect section-like patterns from text."""
    sections: list[SectionInfo] = []
    lines = text.split("\n")
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Heuristic: lines that are short, start with numbers/digits, or are uppercase
        if (len(stripped) < 80 and (
            stripped[0].isdigit() or
            stripped.isupper() or
            stripped.startswith("第") or
            "章" in stripped[:10] or
            "节" in stripped[:10]
        )):
            # Determine level from numbering pattern
            level = 1
            if stripped.startswith("  ") or stripped.startswith("\t"):
                level = 2
            sections.append(SectionInfo(title=stripped, level=level))
            if len(sections) > 50:
                break  # Limit to avoid false positives
    return sections
