"""Token counter using tiktoken or character-based estimation (M2-22).

Supports Chinese + English mixed text.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Rough character-to-token ratios for estimation
# English: ~4 chars per token
# Chinese: ~1.5 chars per token (each character is roughly 1-2 tokens)
# Mixed: ~2.5 chars per token (conservative estimate)


def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken, falling back to character estimation.

    Args:
        text: Input text (Chinese + English mixed).

    Returns:
        Estimated token count.
    """
    if not text:
        return 0

    try:
        import tiktoken
        # Use cl100k_base (GPT-4/Claude-compatible) encoding
        try:
            enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            enc = tiktoken.get_encoding("o200k_base")  # Newer encoding
        return len(enc.encode(text))
    except (ImportError, Exception):
        return _estimate_tokens(text)


def _estimate_tokens(text: str) -> int:
    """Character-based token estimation for Chinese + English mixed text.

    Uses a weighted approach:
    - Chinese characters, Japanese, Korean: ~1.5 chars per token
    - English/ASCII: ~4 chars per token
    - Mixed default: ~2.5 chars per token
    """
    if not text:
        return 0

    # Count CJK characters
    cjk_count = sum(1 for c in text if _is_cjk(c))
    ascii_count = sum(1 for c in text if ord(c) < 128)

    # Estimate tokens
    cjk_tokens = cjk_count / 1.5
    ascii_tokens = ascii_count / 4.0

    return max(1, int(cjk_tokens + ascii_tokens))


def _is_cjk(char: str) -> bool:
    """Check if a character is CJK (Chinese, Japanese, Korean)."""
    cp = ord(char)
    return (
        (0x4E00 <= cp <= 0x9FFF) or    # CJK Unified Ideographs
        (0x3400 <= cp <= 0x4DBF) or    # CJK Unified Ideographs Extension A
        (0x20000 <= cp <= 0x2A6DF) or  # CJK Unified Ideographs Extension B
        (0x2A700 <= cp <= 0x2B73F) or  # CJK Unified Ideographs Extension C
        (0x2B740 <= cp <= 0x2B81F) or  # CJK Unified Ideographs Extension D
        (0x3040 <= cp <= 0x309F) or    # Hiragana
        (0x30A0 <= cp <= 0x30FF) or    # Katakana
        (0xAC00 <= cp <= 0xD7AF) or    # Hangul Syllables
        (0xF900 <= cp <= 0xFAFF) or    # CJK Compatibility Ideographs
        (0xFF00 <= cp <= 0xFFEF)       # Halfwidth and Fullwidth Forms
    )
