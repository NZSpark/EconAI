"""Tesseract OCR processor (M2-17).

Handles image-based PDFs and image files, extracting text with page mapping.
Uses chi_sim+eng language configuration.
"""

from __future__ import annotations

import logging
from importlib.util import find_spec
from typing import Any

from document_service.models import PageContent, ParsedContent
from document_service.parsers.base import BaseParser

logger = logging.getLogger(__name__)


class OCRProcessor(BaseParser):
    """Process image-based PDFs and image files using Tesseract OCR."""

    def __init__(self, language: str = "chi_sim+eng"):
        self._language = language

    def supported_format(self) -> str:
        return "image"

    def parse(self, file_data: bytes, filename: str) -> ParsedContent:
        """Run OCR on image files or image-based PDFs.

        For PDFs: renders each page as an image, then OCRs each page.
        For images: OCRs the single image.
        """
        if find_spec("fitz") is None:
            raise ImportError("PyMuPDF is required for OCR image rendering")

        # Check if it's a PDF (image-based) or an individual image
        if file_data[:4] == b"%PDF":
            return self._ocr_pdf(file_data, filename)
        else:
            return self._ocr_image(file_data, filename)

    def _ocr_pdf(self, file_data: bytes, filename: str) -> ParsedContent:
        """OCR each page of an image-based PDF."""
        import fitz

        try:
            doc = fitz.open(stream=file_data, filetype="pdf")
        except Exception as e:
            logger.warning("Cannot open PDF for OCR, falling back to image OCR: %s", e)
            return self._ocr_image(file_data, filename)

        pages: list[PageContent] = []
        full_text_parts: list[str] = []

        for page_num in range(len(doc)):
            page = doc[page_num]

            # Try text extraction first
            text = page.get_text()
            if text.strip():
                pages.append(PageContent(
                    page_number=page_num + 1,
                    text=text,
                    has_text_layer=True,
                ))
                full_text_parts.append(text)
            else:
                # Render page to image and OCR
                try:
                    pix = page.get_pixmap(dpi=300)
                    img_bytes = pix.tobytes("png")
                    ocr_text = self._run_tesseract(img_bytes, pix.width, pix.height)
                    pages.append(PageContent(
                        page_number=page_num + 1,
                        text=ocr_text,
                        has_text_layer=False,
                    ))
                    full_text_parts.append(ocr_text)
                except Exception as e:
                    logger.warning("OCR failed for page %d: %s", page_num + 1, e)
                    pages.append(PageContent(
                        page_number=page_num + 1,
                        text=f"[OCR Failed: {e}]",
                        has_text_layer=False,
                    ))
                    full_text_parts.append(f"[OCR Failed: {e}]")

        doc.close()

        full_text = "\n\n".join(full_text_parts)

        return ParsedContent(
            full_text=full_text,
            pages=pages,
            tables=[],
            sections=[],
            metadata_hints={"title": filename, "ocr_processed": True},
            needs_ocr=True,
        )

    def _ocr_image(self, file_data: bytes, filename: str) -> ParsedContent:
        """OCR a single image file."""
        try:
            import io as io_module

            from PIL import Image

            pil_img_raw = Image.open(io_module.BytesIO(file_data))
            # Convert to RGB if necessary
            if pil_img_raw.mode not in ("RGB", "L"):
                pil_img: Image.Image = pil_img_raw.convert("RGB")
            else:
                pil_img = pil_img_raw

            # Save as PNG for Tesseract
            png_buffer = io_module.BytesIO()
            pil_img.save(png_buffer, format="PNG")
            png_bytes = png_buffer.getvalue()

            ocr_text = self._run_tesseract(png_bytes, pil_img.width, pil_img.height)

            return ParsedContent(
                full_text=ocr_text,
                pages=[PageContent(page_number=1, text=ocr_text, has_text_layer=False)],
                tables=[],
                sections=[],
                metadata_hints={"title": filename, "ocr_processed": True},
                needs_ocr=True,
            )
        except Exception as e:
            logger.warning("OCR failed for image %s: %s", filename, e)
            return ParsedContent(
                full_text=f"[OCR Failed: {e}]",
                pages=[PageContent(page_number=1, text=f"[OCR Failed: {e}]", has_text_layer=False)],
                tables=[],
                sections=[],
                metadata_hints={"title": filename},
                needs_ocr=True,
            )

    def _run_tesseract(self, image_bytes: bytes, width: int, height: int) -> str:
        """Run Tesseract OCR on image bytes.

        Returns extracted text. Falls back gracefully if Tesseract isn't available.
        """
        try:
            import io as io_module

            import pytesseract
            from PIL import Image

            img = Image.open(io_module.BytesIO(image_bytes))
            text: str = pytesseract.image_to_string(
                img,
                lang=self._language,
                config="--psm 6",  # Assume uniform block of text
            )
            return text.strip()
        except ImportError:
            logger.warning("pytesseract not available; returning empty OCR result")
            return "[OCR not available: pytesseract not installed]"
        except Exception as e:
            logger.warning("Tesseract OCR error: %s", e)
            return f"[OCR Error: {e}]"

    def extract_metadata_hints(self, file_data: bytes, filename: str) -> dict[str, Any]:
        return {"title": filename}
