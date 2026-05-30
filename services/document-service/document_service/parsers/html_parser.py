"""HTML/MHTML parser using BeautifulSoup (M2-16).

Extracts body text (removes navigation, ads, scripts), original links,
and data-URI embedded images with OCR recognition.
"""

from __future__ import annotations

import logging
from typing import Any

from document_service.models import PageContent, ParsedContent, SectionInfo
from document_service.parsers.base import BaseParser
from document_service.parsers.image_extractor import extract_images_from_html

logger = logging.getLogger(__name__)

# Tags/elements to remove (navigation, ads, scripts, etc.)
REMOVE_TAGS = [
    "script", "style", "nav", "header", "footer", "aside",
    "noscript", "iframe", "form", "button",
]

REMOVE_CLASSES = [
    "nav", "navigation", "sidebar", "footer", "header",
    "advertisement", "ad", "banner", "cookie", "menu",
    "social", "share", "comment", "related",
]


class HTMLParser(BaseParser):
    """解析 HTML and MHTML files using BeautifulSoup."""

    def supported_format(self) -> str:
        return "html"

    def parse(self, file_data: bytes, filename: str) -> ParsedContent:
        try:
            from bs4 import BeautifulSoup
        except ImportError as e:
            raise ImportError("BeautifulSoup4 is required for HTML parsing") from e

        # Decode content
        try:
            html_text = file_data.decode("utf-8")
        except UnicodeDecodeError:
            html_text = file_data.decode("latin-1", errors="replace")

        soup = BeautifulSoup(html_text, "lxml")

        # Extract title
        title = ""
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            title = title_tag.string.strip()

        # Remove unwanted elements
        for tag in REMOVE_TAGS:
            for element in soup.find_all(tag):
                element.decompose()

        # Remove elements with unwated classes
        for class_name in REMOVE_CLASSES:
            for element in soup.find_all(class_=lambda c, cn=class_name: c and cn in str(c).lower()):
                element.decompose()

        # Extract links
        links: list[str] = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "")
            if href and isinstance(href, str):
                links.append(str(href))

        # Extract headings for section structure
        sections: list[SectionInfo] = []
        for level in range(1, 7):
            for heading in soup.find_all(f"h{level}"):
                heading_text = heading.get_text(strip=True)
                if heading_text:
                    sections.append(SectionInfo(title=heading_text, level=level))

        # Get body text
        body = soup.find("body")
        body_text = body.get_text(separator="\n", strip=True) if body else soup.get_text(separator="\n", strip=True)

        # 清理 excessive whitespace
        lines = [line.strip() for line in body_text.split("\n") if line.strip()]
        clean_text = "\n".join(lines)

        full_text = clean_text
        if title:
            full_text = f"# {title}\n\n{clean_text}"

        # ---- Extract and OCR data-URI images ----
        ocr_images = extract_images_from_html(file_data)
        if ocr_images:
            image_texts = []
            for img in ocr_images:
                ocr_text = img.get("ocr_text", "")
                if ocr_text and "[OCR" not in ocr_text:
                    image_texts.append(
                        f"[Inline Image {img.get('image_index', 0)} OCR ({img.get('format', 'png')})]:\n{ocr_text}"
                    )
            if image_texts:
                full_text += "\n\n--- Inline Images (OCR) ---\n\n" + "\n\n".join(image_texts)
            logger.info("HTML: OCR'd %d data-URI images", len(ocr_images))
        # ---- End image extraction ----

        return ParsedContent(
            full_text=full_text,
            pages=[PageContent(page_number=1, text=full_text, has_text_layer=True)],
            tables=[],
            sections=sections,
            metadata_hints={
                "title": title,
                "source": links[0] if links else "",
                "html_metadata": {
                    "title": title,
                    "links": links[:20],  # Top 20 links
                    "link_count": len(links),
                },
            },
            needs_ocr=False,
            ocr_images=ocr_images,
        )

    def extract_metadata_hints(self, file_data: bytes, filename: str) -> dict[str, Any]:
        return {}
