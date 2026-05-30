"""Parser router (M2-18).

Automatically selects the correct parser based on identified format.
Returns unified ParsedContent objects.
"""

from __future__ import annotations

import logging

from shared.models import DocumentFormat

from document_service.errors import DocFormatUnsupportedError
from document_service.format_identifier import identify_format, needs_ocr
from document_service.models import ParsedContent
from document_service.parsers.base import BaseParser
from document_service.parsers.email_parser import EmailParser
from document_service.parsers.excel_parser import ExcelParser
from document_service.parsers.html_parser import HTMLParser
from document_service.parsers.markdown_parser import MarkdownParser
from document_service.parsers.ocr_processor import OCRProcessor
from document_service.parsers.pdf_parser import PDFParser
from document_service.parsers.ppt_parser import PPTParser
from document_service.parsers.word_parser import WordParser

logger = logging.getLogger(__name__)


# Registry of parsers
PARSER_REGISTRY: dict[DocumentFormat, BaseParser] = {
    DocumentFormat.pdf: PDFParser(),
    DocumentFormat.docx: WordParser(),
    DocumentFormat.markdown: MarkdownParser(),
    DocumentFormat.txt: MarkdownParser(),  # txt uses same parser
    DocumentFormat.xlsx: ExcelParser(),
    DocumentFormat.csv: ExcelParser(),
    DocumentFormat.pptx: PPTParser(),
    DocumentFormat.eml: EmailParser(),
    DocumentFormat.html: HTMLParser(),
    DocumentFormat.mhtml: HTMLParser(),
    DocumentFormat.image: OCRProcessor(),
}


def get_parser(magic_bytes: bytes, extension: str) -> BaseParser | None:
    """获取 the parser for a given file based on magic bytes and extension.

    Returns None if no parser is registered for the format.
    """
    try:
        fmt = identify_format(magic_bytes, extension)
    except ValueError:
        return None

    parser = PARSER_REGISTRY.get(fmt)
    if parser is None:
        raise DocFormatUnsupportedError(fmt.value)
    return parser


def parse_document(file_data: bytes, filename: str, extension: str) -> ParsedContent:
    """Route to the correct parser and parse the document.

    Args:
        file_data: Raw file bytes.
        filename: Original filename.
        extension: Lowercase extension including dot.

    Returns:
        ParsedContent with extracted text and structure.

    Raises:
        DocFormatUnsupportedError: If no parser is available for the format.
    """
    magic_bytes = file_data[:8]

    # Check if OCR is needed
    if needs_ocr(magic_bytes, extension, file_data):
        fmt = identify_format(magic_bytes, extension)
        if fmt == DocumentFormat.image or fmt == DocumentFormat.pdf:
            ocr_parser = OCRProcessor()
            return ocr_parser.parse(file_data, filename)

    # Get appropriate parser
    selected_parser = get_parser(magic_bytes, extension)
    if selected_parser is None:
        raise DocFormatUnsupportedError(extension)

    parser: BaseParser = selected_parser
    logger.info("Routing %s to parser %s", filename, parser.__class__.__name__)
    return parser.parse(file_data, filename)


def register_parser(fmt: DocumentFormat, parser: BaseParser) -> None:
    """注册 a custom parser for a format."""
    PARSER_REGISTRY[fmt] = parser
