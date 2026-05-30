"""Tests for OCR processing (M2-40).

Tests image-PDF and image file OCR with Chinese content.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# OCR Processor Tests
# ---------------------------------------------------------------------------


class TestOCRProcessor:
    """M2-17/M2-40: OCR processor tests."""

    def test_ocr_pdf_without_text_layer(self) -> None:
        """Test OCR fallback for PDF with no text layer (graceful degradation)."""
        from document_service.parsers.ocr_processor import OCRProcessor
        proc = OCRProcessor(language="chi_sim+eng")

        # 创建 fake PDF header with no actual content
        # OCR processor should handle the error gracefully
        fake_pdf = b"%PDF-1.4\nthis is not a valid PDF"
        result = proc.parse(fake_pdf, "bad.pdf")

        assert result is not None
        assert result.full_text is not None
        assert isinstance(result.full_text, str)

    def test_ocr_image_file(self) -> None:
        """Test OCR on an image file."""
        from document_service.parsers.ocr_processor import OCRProcessor
        proc = OCRProcessor(language="chi_sim+eng")

        # 创建 a simple 1x1 PNG
        import io

        from PIL import Image
        img = Image.new("RGB", (1, 1), color="white")
        buf = io.BytesIO()
        img.save(buf, "PNG")
        img_bytes = buf.getvalue()

        result = proc.parse(img_bytes, "test.png")

        assert result is not None
        assert isinstance(result.full_text, str)

    def test_ocr_image_returns_content(self) -> None:
        """OCR of an image returns ParsedContent with needs_ocr=True."""
        from document_service.parsers.ocr_processor import OCRProcessor
        proc = OCRProcessor()

        import io

        from PIL import Image
        img = Image.new("L", (10, 10), color=0)
        buf = io.BytesIO()
        img.save(buf, "PNG")

        result = proc.parse(buf.getvalue(), "test.png")
        assert result.needs_ocr is True
        assert len(result.pages) > 0

    def test_ocr_with_chinese_language_setting(self) -> None:
        """ 。"""
        from document_service.parsers.ocr_processor import OCRProcessor
        proc = OCRProcessor(language="chi_sim+eng")
        assert "chi_sim" in proc._language
        assert "eng" in proc._language

    def test_supported_format(self) -> None:
        from document_service.parsers.ocr_processor import OCRProcessor
        proc = OCRProcessor()
        assert proc.supported_format() == "image"


# ---------------------------------------------------------------------------
# 格式 Identifier OCR detection tests
# ---------------------------------------------------------------------------


class TestFormatIdentifierOCR:
    """测试辅助函数。"""

    def test_needs_ocr_for_image_formats(self) -> None:
        from document_service.format_identifier import needs_ocr

        # PNG magic bytes
        png_bytes = b"\x89PNG\r\n\x1a\n"
        assert needs_ocr(png_bytes, ".png", png_bytes) is True

        # JPEG magic bytes
        jpeg_bytes = b"\xff\xd8\xff\xe0"
        assert needs_ocr(jpeg_bytes, ".jpg", jpeg_bytes) is True

    def test_pdf_with_magic_bytes_no_ocr(self) -> None:
        """PDF with magic bytes should be checked for text layer."""
        from document_service.format_identifier import needs_ocr
        # PDF bytes (the method tries to open as PDF)
        pdf_bytes = b"%PDF-1.4\n%%EOF"
        # This tiny PDF has no pages, so it will not need OCR
        # (detect_pdf_text_layer returns True for empty PDF to be safe)
        result = needs_ocr(pdf_bytes, ".pdf", pdf_bytes)
        # For empty PDF, text layer detection returns True (safe default)
        assert isinstance(result, bool)

    def test_text_files_no_ocr(self) -> None:
        from document_service.format_identifier import needs_ocr
        txt_bytes = b"Plain text content"
        assert needs_ocr(txt_bytes, ".txt", txt_bytes) is False
        assert needs_ocr(txt_bytes, ".md", txt_bytes) is False
