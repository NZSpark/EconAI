"""格式化 identification module (M2-08, M2-09).

Magic bytes detection + extension fallback -> unified format enum.
PDF text layer detection via PyMuPDF.
"""

from __future__ import annotations

import logging

from shared.models import DocumentFormat

from document_service.models import EXTENSION_FORMAT_MAP, MAGIC_BYTES

logger = logging.getLogger(__name__)


def identify_format(magic_bytes: bytes, extension: str) -> DocumentFormat:
    """Identify document format using magic bytes first, then extension fallback.

    Args:
        magic_bytes: First 8 bytes of the file.
        extension: Lowercase file extension including dot (e.g., ".pdf").

    Returns:
        DocumentFormat enum value.

    Raises:
        ValueError: If format cannot be determined.
    """
    # Try magic bytes first
    for signature, fmt in MAGIC_BYTES.items():
        if magic_bytes.startswith(signature):
            # ZIP-based formats need extension to disambiguate
            if signature == b"\x50\x4b\x03\x04":
                if extension in (".docx", ".doc"):
                    return DocumentFormat.docx
                if extension in (".xlsx", ".xls", ".csv"):
                    return DocumentFormat.xlsx
                if extension in (".pptx", ".ppt"):
                    return DocumentFormat.pptx
                # CSV is plain text, but if magic bytes match ZIP it's likely an OOXML spreadsheet
                return DocumentFormat.docx  # 默认 ZIP -> docx

            # OLE2 format
            if signature == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                if extension in (".doc", ".docx"):
                    return DocumentFormat.docx
                if extension in (".xls", ".xlsx"):
                    return DocumentFormat.xlsx
                if extension in (".ppt", ".pptx"):
                    return DocumentFormat.pptx

            return fmt  # PDF has distinct magic bytes

    # No magic byte match — use extension fallback
    fallback_fmt: DocumentFormat | None = EXTENSION_FORMAT_MAP.get(extension)
    if fallback_fmt is None:
        raise ValueError(f"Cannot identify format for extension '{extension}'")
    return fallback_fmt


def detect_pdf_text_layer(file_data: bytes) -> bool:
    """M2-09: Detect whether a PDF has an extractable text layer using PyMuPDF.

    Args:
        file_data: Raw PDF file bytes.

    Returns:
        True if text layer is present, False if OCR is needed.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF not available, assuming text layer present")
        return True

    try:
        doc = fitz.open(stream=file_data, filetype="pdf")
        total_text = ""
        # Check first 5 pages for text presence
        pages_to_check = min(5, len(doc))
        for i in range(pages_to_check):
            page = doc[i]
            total_text += page.get_text()
            if len(total_text.strip()) > 50:
                doc.close()
                return True
        doc.close()
        return len(total_text.strip()) > 0
    except Exception as e:
        logger.warning("PDF text layer detection failed: %s, assuming text layer present", e)
        return True


def needs_ocr(magic_bytes: bytes, extension: str, file_data: bytes) -> bool:
    """Determine if a file needs OCR processing.

    Returns True for:
      - Image formats (.png, .jpg, .jpeg, .tiff, .bmp)
      - PDFs without text layer
    """
    format_type = identify_format(magic_bytes, extension)

    if format_type == DocumentFormat.image:
        return True

    if format_type == DocumentFormat.pdf:
        return not detect_pdf_text_layer(file_data)

    return False
