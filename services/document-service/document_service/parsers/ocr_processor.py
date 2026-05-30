"""Tesseract OCR 处理器（M2-17）。

处理扫描版 PDF 和图片文件，通过 OCR 提取文本并映射到页码。
使用 chi_sim+eng 语言配置（中文简体 + 英文）。
"""

from __future__ import annotations

import logging
from importlib.util import find_spec
from typing import Any

from document_service.models import PageContent, ParsedContent
from document_service.parsers.base import BaseParser

logger = logging.getLogger(__name__)


class OCRProcessor(BaseParser):
    """使用 Tesseract OCR 处理扫描版 PDF 和图片文件。
    
    处理流程：
    1. 检测文件类型（PDF vs 图片）
    2. PDF：先用 PyMuPDF 提取文本层，如果为空则渲染为图片再 OCR
    3. 图片：直接用 Tesseract OCR 识别
    4. 每页结果记录到 PageContent，标记 has_text_layer
    """

    def __init__(self, language: str = "chi_sim+eng"):
        self._language = language

    def supported_format(self) -> str:
        return "image"

    def parse(self, file_data: bytes, filename: str) -> ParsedContent:
        """对图片文件或扫描版 PDF 运行 OCR。"""
        if find_spec("fitz") is None:
            raise ImportError("PyMuPDF is required for OCR image rendering")

        # 判断文件类型：PDF 魔术字节为 %PDF
        if file_data[:4] == b"%PDF":
            return self._ocr_pdf(file_data, filename)
        else:
            return self._ocr_image(file_data, filename)

    def _ocr_pdf(self, file_data: bytes, filename: str) -> ParsedContent:
        """逐页 OCR 扫描版 PDF。
        
        对每一页：
        1. 先尝试提取文本层（有些扫描 PDF 嵌入了 OCR 文本）
        2. 如果文本层为空 → 渲染为 300 DPI 图片 → Tesseract OCR
        """
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

            # 优先尝试直接提取文本（有些 PDF 内嵌了文本层）
            text = page.get_text()
            if text.strip():
                pages.append(PageContent(
                    page_number=page_num + 1,
                    text=text,
                    has_text_layer=True,
                ))
                full_text_parts.append(text)
            else:
                # 文本层为空 → 渲染为图片 → OCR 识别
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
        """OCR 识别单张图片文件。"""
        try:
            import io as io_module

            from PIL import Image

            pil_img_raw = Image.open(io_module.BytesIO(file_data))
            # 统一转为 RGB 模式（Tesseract 需要）
            if pil_img_raw.mode not in ("RGB", "L"):
                pil_img: Image.Image = pil_img_raw.convert("RGB")
            else:
                pil_img = pil_img_raw

            # 转为 PNG 字节流供 Tesseract 使用
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
        """运行 Tesseract OCR 识别图片中的文字。
        
        委托给 image_extractor 中的 ocr_image_bytes 辅助函数，
        确保所有解析器的 OCR 行为一致。
        """
        from document_service.parsers.image_extractor import ocr_image_bytes

        return ocr_image_bytes(image_bytes, self._language)

    def extract_metadata_hints(self, file_data: bytes, filename: str) -> dict[str, Any]:
        return {"title": filename}
