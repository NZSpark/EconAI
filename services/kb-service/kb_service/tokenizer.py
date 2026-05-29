"""Chinese-aware tokenization for BM25 search and highlight generation.

Uses jieba for Chinese text segmentation and whitespace-splitting for
Latin/CJK-unmixed text. Provides a unified tokenize() function that
both the BM25 searcher and the highlight generator can share.
"""

from __future__ import annotations

import logging
import re
from typing import NamedTuple

logger = logging.getLogger(__name__)

# CJK Unicode ranges: Chinese, Japanese, Korean
_CJK_RE = re.compile(r"[一-鿿㐀-䶿豈-﫿]")


def contains_cjk(text: str) -> bool:
    """Check whether *text* contains any CJK characters."""
    return bool(_CJK_RE.search(text))


# ---------------------------------------------------------------------------
# jieba is imported lazily so that tests / non-CJK codepaths don't require it
# to be installed (though it is a declared dependency).
# ---------------------------------------------------------------------------

_jieba_loaded: bool | None = None


def _ensure_jieba() -> None:
    global _jieba_loaded
    if _jieba_loaded is not None:
        return
    try:
        import jieba  # type: ignore[import-untyped]
        import jieba.analyse  # noqa: F401

        jieba.setLogLevel(logging.WARNING)
        _jieba_loaded = True
    except ImportError:
        _jieba_loaded = False
        logger.warning("jieba not available; Chinese tokenization will fall back to whitespace-splitting")


def tokenize(text: str) -> list[str]:
    """Split *text* into a list of tokens.

    - If the text contains CJK characters and jieba is available, use
      jieba.lcut for Chinese word segmentation.
    - Otherwise fall back to whitespace-based splitting.

    Returns only tokens that contain at least one alphanumeric character.
    """
    if not text:
        return []

    _ensure_jieba()

    if _jieba_loaded and contains_cjk(text):
        import jieba  # type: ignore[import-untyped]

        raw_tokens: list[str] = jieba.lcut(text)
    else:
        raw_tokens = text.split()

    return [t.strip() for t in raw_tokens if t.strip() and any(c.isalnum() for c in t)]


# ---------------------------------------------------------------------------
# Highlight helpers
# ---------------------------------------------------------------------------


class HighlightSpan(NamedTuple):
    """A matched span: start/end indices (char-based) within the original text."""

    start: int
    end: int


def find_highlight_spans(text: str, query: str) -> list[HighlightSpan]:
    """Locate every occurrence of query terms within *text*.

    Uses the same tokenize() logic to extract query tokens, then does
    case-insensitive substring search for each token.
    """
    if not text or not query:
        return []

    tokens = tokenize(query)
    if not tokens:
        return []

    text_lower = text.lower()
    spans: list[HighlightSpan] = []

    for tok in tokens:
        tok_lower = tok.lower()
        start = 0
        while True:
            pos = text_lower.find(tok_lower, start)
            if pos == -1:
                break
            spans.append(HighlightSpan(pos, pos + len(tok)))
            start = pos + 1

    # Deduplicate overlapping spans
    spans.sort()
    merged: list[HighlightSpan] = []
    for s in spans:
        if not merged:
            merged.append(s)
            continue
        last = merged[-1]
        if s.start <= last.end:
            merged[-1] = HighlightSpan(last.start, max(last.end, s.end))
        else:
            merged.append(s)
    return merged


def apply_highlight(text: str, spans: list[HighlightSpan], tag: str = "em") -> str:
    """Wrap matched spans in *text* with HTML-style <tag>...</tag> markers.

    Returns the highlighted text with non-overlapping spans wrapped.
    """
    if not spans:
        return text

    result: list[str] = []
    cursor = 0
    for s in sorted(spans):
        result.append(text[cursor : s.start])
        result.append(f"<{tag}>")
        result.append(text[s.start : s.end])
        result.append(f"</{tag}>")
        cursor = s.end
    result.append(text[cursor:])
    return "".join(result)


def extract_matched_terms(query: str) -> list[str]:
    """Extract the list of unique tokens from *query* after tokenization.

    This is useful for returning a 'matched_terms' list alongside each
    search result, so the frontend can highlight without re-tokenizing.
    """
    return list(dict.fromkeys(tokenize(query)))  # dedup, preserve order
