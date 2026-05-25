"""File validation module (M2-05).

Validates: extension whitelist, MIME type, file size (100MB max), magic bytes.
"""

from __future__ import annotations

import os
from typing import IO

from document_service.models import ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES, MAGIC_BYTES


class FileValidationError(ValueError):
    """Raised when file validation fails."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def validate_extension(filename: str) -> str:
    """Validate file extension against whitelist.

    Returns the lowercase extension (including dot).
    Raises FileValidationError if the extension is not allowed.
    """
    _, ext = os.path.splitext(filename)
    ext_lower = ext.lower()
    if not ext_lower:
        raise FileValidationError(
            "DOC_NO_EXTENSION",
            "File has no extension.",
        )
    if ext_lower not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            "DOC_FORMAT_UNSUPPORTED",
            f"File extension '{ext_lower}' is not in the allowed list.",
        )
    return ext_lower


def validate_mime_type(mime_type: str | None) -> None:
    """Validate MIME type against whitelist.

    Raises FileValidationError if the MIME type is not allowed.
    If mime_type is None, skip MIME check (extension check already passed).
    Allows 'application/octet-stream' as a generic fallback (common in browsers for
    Office documents and other binary formats where the browser doesn't know the MIME).
    """
    if mime_type is None:
        return
    # Strip charset suffix (e.g., "text/plain; charset=utf-8")
    base_mime = mime_type.split(";")[0].strip().lower()

    # application/octet-stream is a generic fallback — accept it when the
    # extension is valid (extension check runs before this in validate_file)
    if base_mime == "application/octet-stream":
        return

    if base_mime not in ALLOWED_MIME_TYPES:
        raise FileValidationError(
            "DOC_MIME_UNSUPPORTED",
            f"MIME type '{base_mime}' is not in the allowed list.",
        )


def validate_file_size(file_size: int, max_size_mb: int = 100) -> None:
    """Validate file size is within limits.

    Raises FileValidationError if the file exceeds the maximum size.
    """
    max_bytes = max_size_mb * 1024 * 1024
    if file_size > max_bytes:
        raise FileValidationError(
            "DOC_FILE_TOO_LARGE",
            f"File size ({file_size} bytes) exceeds maximum allowed ({max_bytes} bytes, {max_size_mb}MB).",
        )
    if file_size == 0:
        raise FileValidationError(
            "DOC_FILE_EMPTY",
            "File is empty (0 bytes).",
        )


def read_magic_bytes(file_obj: IO[bytes], num_bytes: int = 8) -> bytes:
    """Read the first num_bytes from a file object and reset position.

    Returns at most num_bytes of magic bytes.
    """
    current_pos = file_obj.tell()
    magic = file_obj.read(num_bytes)
    file_obj.seek(current_pos)
    return magic


def validate_magic_bytes(magic: bytes, extension: str) -> None:
    """Validate magic bytes match expected format for the extension.

    Checks magic bytes against known signatures. If magic doesn't match
    any known format, falls back to extension-based identification.
    Raises FileValidationError only when both magic and extension are unrecognizable.
    """
    for signature in MAGIC_BYTES:
        if magic.startswith(signature):
            # ZIP-based formats (.docx/.xlsx/.pptx) need extension to disambiguate
            if signature == b"\x50\x4b\x03\x04" and extension in (
                ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt",
            ):
                return  # Valid ZIP-based office format
            return  # Valid known format

    # If no magic match, check if extension is still valid by itself.
    # Some file types don't have distinctive magic bytes or have variable headers
    # that make simple signature matching unreliable (text files, images, etc.)
    extension_bypass = {
        ".txt", ".md", ".csv", ".html", ".eml", ".mhtml", ".mht",
        ".png", ".jpg", ".jpeg", ".tiff", ".bmp",
    }
    if extension in extension_bypass:
        return  # Valid extension, no further magic byte check needed

    raise FileValidationError(
        "DOC_MAGIC_MISMATCH",
        f"File magic bytes do not match expected format for extension '{extension}'.",
    )


def validate_file(filename: str, mime_type: str | None, file_size: int, magic: bytes, max_size_mb: int = 100) -> str:
    """Run all file validations.

    Returns the validated (lowercase) extension.
    Raises FileValidationError on any validation failure.
    """
    ext = validate_extension(filename)
    validate_mime_type(mime_type)
    validate_file_size(file_size, max_size_mb)
    validate_magic_bytes(magic, ext)
    return ext
