"""Inline citation parser (M6-03 through M6-07).

Implements:
  - Sentence splitter for Chinese and English punctuation (M6-03)
  - Regex extractor for [ref:...] markers (M6-04)
  - Citation marker parsing (doc_id + page_range extraction) (M6-05)
  - CitationParser main flow: text -> sentences -> citations -> mapping (M6-06)
  - Edge case handling: no refs, malformed refs (M6-07)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# M6-03: Sentence splitter - Chinese and English punctuation
# ---------------------------------------------------------------------------

# Split after 。！？! ? (but NOT after "." preceded by a digit, to avoid
# splitting on decimal points like "3.5%").
_SENTENCE_END_RE = re.compile(r"(?<=[。！？!?]|(?<!\d)\.(?=\s|$))\s*")

# Note: This simplistic approach handles Chinese/English sentence-ending punctuation.
# For production, a more robust splitter (e.g., spaCy) would be used, but the design
# docs specify this regex-based approach for the MVP.


def split_sentences(text: str) -> list[str]:
    """Split text into sentences using Chinese/English punctuation boundaries.

    Args:
        text: Raw LLM output text, possibly containing [ref:...] markers.

    Returns:
        List of sentence strings (whitespace-trimmed, non-empty).
    """
    raw_parts = _SENTENCE_END_RE.split(text)
    sentences: list[str] = []
    for part in raw_parts:
        stripped = part.strip()
        if stripped:
            sentences.append(stripped)
    return sentences


# ---------------------------------------------------------------------------
# M6-04: Regex extractor for [ref:...] markers
# ---------------------------------------------------------------------------

# Matches: [ref:doc_id:page_range], [ref:doc_id:page|doc_id:page], [ref:uncertain]
_REF_PATTERN = re.compile(r"\[ref:([^\]]+)\]")

# Matches a single doc_ref: doc_id:page_range
_DOC_REF_PATTERN = re.compile(r"^([^:]+):(.+)$")


# ---------------------------------------------------------------------------
# M6-05: Citation marker parsing (doc_id + page_range, multi-ref with |)
# ---------------------------------------------------------------------------

@dataclass
class DocRef:
    """A single document reference within a citation marker."""

    doc_id: str
    page_range: str  # e.g. "45-48", "12", "33-35"


@dataclass
class CitationRef:
    """Parsed citation reference from inline [ref:...] marker."""

    raw_mark: str  # The full text inside [ref:...]
    is_uncertain: bool = False
    doc_refs: list[DocRef] = field(default_factory=list)
    parse_error: str | None = None


@dataclass
class SentenceCitation:
    """A sentence with its associated parsed citations."""

    sentence: str
    sentence_index: int
    citations: list[CitationRef] = field(default_factory=list)


def parse_ref_mark(raw_mark: str) -> CitationRef:
    """Parse a single [ref:...] marker content.

    Handles:
      - "doc_123:p45-48"           -> single reference
      - "doc_456:p12|doc_789:p33"  -> multi-reference
      - "uncertain"                -> uncertain declaration
      - Malformed marks            -> parse_error set

    Args:
        raw_mark: The text content inside [ref:...].

    Returns:
        A CitationRef with parsed doc_refs or parse_error.
    """
    ref = CitationRef(raw_mark=raw_mark.strip())

    # Special case: uncertain
    if ref.raw_mark.lower() == "uncertain":
        ref.is_uncertain = True
        return ref

    # Split multi-references by |
    parts = ref.raw_mark.split("|")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = _DOC_REF_PATTERN.match(part)
        if not m:
            ref.parse_error = f"Malformed ref marker: '{part}' in '{ref.raw_mark}'"
            return ref
        doc_id = m.group(1).strip()
        page_range = m.group(2).strip()
        if not doc_id or not page_range:
            ref.parse_error = f"Empty doc_id or page_range in '{part}'"
            return ref
        ref.doc_refs.append(DocRef(doc_id=doc_id, page_range=page_range))

    if not ref.doc_refs and not ref.is_uncertain:
        ref.parse_error = f"No valid doc_refs found in '{ref.raw_mark}'"

    return ref


def extract_refs_from_sentence(sentence: str) -> list[CitationRef]:
    """Extract all [ref:...] markers from a sentence and parse them.

    Args:
        sentence: A single sentence that may contain [ref:...] markers.

    Returns:
        List of parsed CitationRef objects.
    """
    raw_marks = _REF_PATTERN.findall(sentence)
    refs: list[CitationRef] = []
    for raw_mark in raw_marks:
        refs.append(parse_ref_mark(raw_mark))
    return refs


# ---------------------------------------------------------------------------
# M6-06/M6-07: CitationParser main flow
# ---------------------------------------------------------------------------


@dataclass
class CitationParserResult:
    """Complete result from parsing inline citations."""

    sentences: list[SentenceCitation]
    total_sentences: int
    sentences_with_refs: int
    total_refs: int
    parse_errors: list[dict[str, str]]  # {"sentence_index": N, "error": "..."}


class CitationParser:
    """Parses inline [ref:...] citations from LLM output text.

    Flow: text -> split sentences -> extract refs -> build sentence->doc_refs mapping.
    """

    def parse(self, text: str) -> CitationParserResult:
        """Parse inline citations from the full output text.

        Args:
            text: LLM output containing [ref:...] markers.

        Returns:
            CitationParserResult with structured sentences, citations, and error info.
        """
        sentences = split_sentences(text)
        parsed_sentences: list[SentenceCitation] = []
        parse_errors: list[dict[str, str]] = []
        total_refs = 0
        sentences_with_refs = 0

        for idx, sentence in enumerate(sentences):
            refs = extract_refs_from_sentence(sentence)
            sent_refs: list[CitationRef] = []
            has_refs = False

            for ref in refs:
                if ref.parse_error:
                    # M6-07: Record parse errors for malformed refs
                    parse_errors.append(
                        {
                            "sentence_index": str(idx),
                            "sentence": sentence[:100],
                            "error": ref.parse_error,
                        }
                    )
                else:
                    sent_refs.append(ref)
                    has_refs = True
                    total_refs += 1

            parsed_sentences.append(
                SentenceCitation(
                    sentence=sentence,
                    sentence_index=idx,
                    citations=sent_refs,
                )
            )
            if has_refs:
                sentences_with_refs += 1

        return CitationParserResult(
            sentences=parsed_sentences,
            total_sentences=len(sentences),
            sentences_with_refs=sentences_with_refs,
            total_refs=total_refs,
            parse_errors=parse_errors,
        )
