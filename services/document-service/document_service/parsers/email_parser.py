"""Email (.eml) parser using Python standard library (M2-15).

Extracts body text and metadata (sender, date, subject, recipients).
"""

from __future__ import annotations

import email
import logging
from email.policy import default
from typing import Any

from document_service.models import PageContent, ParsedContent
from document_service.parsers.base import BaseParser

logger = logging.getLogger(__name__)


class EmailParser(BaseParser):
    """Parse .eml files using Python's email standard library."""

    def supported_format(self) -> str:
        return "eml"

    def parse(self, file_data: bytes, filename: str) -> ParsedContent:
        msg = email.message_from_bytes(file_data, policy=default)

        # Extract metadata
        subject = str(msg.get("Subject", ""))
        sender = str(msg.get("From", ""))
        recipients = str(msg.get("To", ""))
        cc = str(msg.get("Cc", ""))
        date_str = str(msg.get("Date", ""))

        # Extract body
        body_text = ""
        html_body = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disposition:
                    continue  # Skip attachments

                try:
                    payload = part.get_content()
                    if content_type == "text/plain" and isinstance(payload, str):
                        body_text += payload + "\n"
                    elif content_type == "text/html" and isinstance(payload, str):
                        html_body += payload + "\n"
                except Exception:
                    # Fallback: try decoding payload
                    try:
                        payload_bytes = part.get_payload(decode=True)
                        if isinstance(payload_bytes, bytes):
                            body_text += payload_bytes.decode("utf-8", errors="replace") + "\n"
                    except Exception:
                        pass
        else:
            try:
                body_text = str(msg.get_content())
            except Exception:
                try:
                    payload_bytes = msg.get_payload(decode=True)
                    if isinstance(payload_bytes, bytes):
                        body_text = payload_bytes.decode("utf-8", errors="replace")
                except Exception:
                    body_text = ""

        # Build structured text
        full_text = f"""Subject: {subject}
From: {sender}
To: {recipients}
Cc: {cc}
Date: {date_str}

{body_text}"""

        return ParsedContent(
            full_text=full_text,
            pages=[PageContent(page_number=1, text=full_text, has_text_layer=True)],
            tables=[],
            sections=[],
            metadata_hints={
                "title": subject,
                "author": sender,
                "date": date_str,
                "source": f"email from {sender}",
                "email_metadata": {
                    "subject": subject,
                    "sender": sender,
                    "recipients": recipients,
                    "cc": cc,
                    "date": date_str,
                },
            },
            needs_ocr=False,
        )

    def extract_metadata_hints(self, file_data: bytes, filename: str) -> dict[str, Any]:
        return {}
