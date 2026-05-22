"""Citation verification and confidence logic (M6-08 through M6-13).

Implements:
  - Page range matching (M6-08)
  - Page overlap calculation (M6-09)
  - Semantic similarity via cosine similarity (M6-10)
  - Confidence classification: direct/fuzzy/uncertain (M6-11)
  - CitationVerifier main flow (M6-12)
  - Verification summary report (M6-13)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from citation_service.parser import CitationParserResult, CitationRef

# ---------------------------------------------------------------------------
# M6-08: Page range matching
# ---------------------------------------------------------------------------

@dataclass
class PageRange:
    """A parsed page range."""

    start: int
    end: int

    @classmethod
    def parse(cls, raw: str) -> PageRange | None:
        """Parse a page range string like '45-48', '12', 'p1-5', or 'p12'.

        Strips non-numeric prefixes (e.g. 'p', 'pp') before parsing.

        Args:
            raw: Page range string.

        Returns:
            PageRange or None if malformed.
        """
        import re as _re_mod

        raw = raw.strip()

        # Strip leading non-digit characters (e.g. 'p' from 'p1-5')
        num_part = _re_mod.sub(r"^[^\d]*", "", raw)

        if "-" in num_part:
            parts = num_part.split("-", 1)
            try:
                start = int(parts[0].strip())
                end = int(parts[1].strip())
            except ValueError:
                return None
            if start > end:
                start, end = end, start
            return cls(start=start, end=end)
        else:
            try:
                page = int(num_part)
            except ValueError:
                return None
            return cls(start=page, end=page)

    def contains(self, other: PageRange) -> bool:
        """Check if this range fully contains other range."""
        return self.start <= other.start and self.end >= other.end

    def overlaps(self, other: PageRange) -> bool:
        """Check if this range overlaps with other range."""
        return self.start <= other.end and other.start <= self.end


def page_range_matches(
    ref_pages: PageRange, chunk_pages: PageRange
) -> bool:
    """Check if chunk.page_start <= ref.page_start and chunk.page_end >= ref.page_end.

    (M6-08: exact page range matching)
    """
    return chunk_pages.contains(ref_pages)


# ---------------------------------------------------------------------------
# M6-09: Page overlap calculation
# ---------------------------------------------------------------------------


def page_overlap(
    ref_pages: PageRange, chunk_pages: PageRange
) -> float:
    """Calculate Jaccard-like page overlap between ref and chunk page ranges.

    Returns a value 0.0-1.0, where 1.0 means identical ranges.

    (M6-09: page overlap when exact match fails)
    """
    if not ref_pages.overlaps(chunk_pages):
        return 0.0

    overlap_start = max(ref_pages.start, chunk_pages.start)
    overlap_end = min(ref_pages.end, chunk_pages.end)
    overlap_len = overlap_end - overlap_start + 1

    ref_len = ref_pages.end - ref_pages.start + 1
    chunk_len = chunk_pages.end - chunk_pages.start + 1
    union_len = ref_len + chunk_len - overlap_len

    if union_len == 0:
        return 0.0
    return overlap_len / union_len


# ---------------------------------------------------------------------------
# M6-10: Semantic similarity via cosine similarity
# ---------------------------------------------------------------------------

# Simple token-based cosine similarity (no external embedding model dependency for MVP).
# In production this would use actual embeddings from the KB service.
# For testing, a mock vector can be injected.


def _simple_tokenize(text: str) -> dict[str, int]:
    """Tokenize text into a bag-of-words frequency map."""
    import re

    tokens = re.findall(r"[一-鿿]+|[a-zA-Z]+", text.lower())
    freq: dict[str, int] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    return freq


def cosine_similarity_sparse(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Compute cosine similarity between two sparse vectors."""
    if not vec_a or not vec_b:
        return 0.0

    dot_product = 0.0
    norm_a_sq = 0.0
    norm_b_sq = 0.0

    for key, val_a in vec_a.items():
        norm_a_sq += val_a * val_a
        dot_product += val_a * vec_b.get(key, 0.0)

    for val_b in vec_b.values():
        norm_b_sq += val_b * val_b

    norm_a = math.sqrt(norm_a_sq)
    norm_b = math.sqrt(norm_b_sq)

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def cosine_similarity_dense(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two dense embedding vectors."""
    if not vec_a or not vec_b:
        return 0.0

    dot_product = sum(x * y for x, y in zip(vec_a, vec_b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in vec_a))
    norm_b = math.sqrt(sum(y * y for y in vec_b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def compute_text_similarity(text_a: str, text_b: str) -> float:
    """Compute cosine similarity between two text strings.

    Uses bag-of-words tokenization as a fallback. When an embedding client
    is available, use compute_text_similarity_with_embeddings() instead.
    """
    vec_a = {k: float(v) for k, v in _simple_tokenize(text_a).items()}
    vec_b = {k: float(v) for k, v in _simple_tokenize(text_b).items()}
    return cosine_similarity_sparse(vec_a, vec_b)


async def compute_text_similarity_with_embeddings(
    text_a: str, text_b: str, embed_fn: Any | None = None
) -> float:
    """Compute semantic similarity using embedding vectors.

    Falls back to bag-of-words when embed_fn is not provided or fails.
    """
    if embed_fn is None:
        return compute_text_similarity(text_a, text_b)

    try:

        vectors = await embed_fn([text_a, text_b])
        if len(vectors) >= 2:
            return cosine_similarity_dense(vectors[0], vectors[1])
    except Exception:
        pass

    return compute_text_similarity(text_a, text_b)


# ---------------------------------------------------------------------------
# M6-11: Confidence classification
# ---------------------------------------------------------------------------


@dataclass
class MatchedChunk:
    """A chunk that was matched during verification."""

    chunk_id: str
    document_id: str
    page_start: int
    page_end: int
    excerpt: str
    similarity: float


@dataclass
class VerifiedCitation:
    """A fully verified citation."""

    ref_id: str
    sentence: str
    sentence_index: int
    confidence: str  # "direct" | "fuzzy" | "uncertain"
    matched_chunks: list[MatchedChunk] = field(default_factory=list)


def determine_confidence(
    has_exact_page_match: bool,
    similarity: float,
    threshold: float,
) -> str:
    """Determine confidence level based on page matching and semantic similarity.

    (M6-11)
    - direct: exact page match AND similarity > threshold
    - fuzzy: similarity > threshold but no exact page match, OR doc_id exists
             but page doesn't match exactly
    - uncertain: no match found at all
    """
    if has_exact_page_match and similarity >= threshold:
        return "direct"
    elif similarity >= threshold:
        return "fuzzy"
    else:
        return "uncertain"


# ---------------------------------------------------------------------------
# Context chunk type for verification
# ---------------------------------------------------------------------------


@dataclass
class ContextChunk:
    """Represents a context chunk provided for verification (from KB service)."""

    chunk_id: str
    document_id: str
    content: str
    page_start: int
    page_end: int


# ---------------------------------------------------------------------------
# M6-12/M6-13: CitationVerifier main flow + summary
# ---------------------------------------------------------------------------


@dataclass
class VerificationSummary:
    """M6-13: Summary report for a verification run."""

    total: int
    direct: int
    fuzzy: int
    uncertain: int


@dataclass
class VerificationResult:
    """Complete verification result."""

    citations: list[VerifiedCitation]
    summary: VerificationSummary


class CitationVerifier:
    """Verifies parsed citations against available context chunks.

    Flow (M6-12):
      1. Accept parsed citations + context chunks
      2. For each citation, find matching chunks
      3. Compute similarity and page overlap
      4. Assign confidence (direct/fuzzy/uncertain)
      5. Generate summary (M6-13)
    """

    def __init__(self, similarity_threshold: float = 0.85):
        self._threshold = similarity_threshold

    def verify(
        self,
        parsed_result: CitationParserResult,
        context_chunks: list[ContextChunk],
    ) -> VerificationResult:
        """Verify all parsed citations against available chunks.

        Args:
            parsed_result: Output from CitationParser.
            context_chunks: Available chunks from the KB service.

        Returns:
            VerificationResult with verified citations and summary.
        """
        verified: list[VerifiedCitation] = []
        chunk_index = self._build_chunk_index(context_chunks)

        for sent_citation in parsed_result.sentences:
            for ref in sent_citation.citations:
                verified_cit = self._verify_single(
                    ref,
                    sent_citation.sentence,
                    sent_citation.sentence_index,
                    chunk_index,
                )
                verified.append(verified_cit)

        return VerificationResult(
            citations=verified,
            summary=self._build_summary(verified),
        )

    def _build_chunk_index(
        self, chunks: list[ContextChunk]
    ) -> dict[str, list[ContextChunk]]:
        """Build a document_id -> chunks index for fast lookup."""
        index: dict[str, list[ContextChunk]] = {}
        for chunk in chunks:
            index.setdefault(chunk.document_id, []).append(chunk)
        return index

    def _verify_single(
        self,
        ref: CitationRef,
        sentence: str,
        sentence_index: int,
        chunk_index: dict[str, list[ContextChunk]],
    ) -> VerifiedCitation:
        """Verify a single citation reference."""
        if ref.is_uncertain:
            return VerifiedCitation(
                ref_id="uncertain",
                sentence=sentence,
                sentence_index=sentence_index,
                confidence="uncertain",
            )

        matched_chunks: list[MatchedChunk] = []
        best_confidence = "uncertain"

        for doc_ref in ref.doc_refs:
            doc_chunks = chunk_index.get(doc_ref.doc_id, [])
            ref_pages = PageRange.parse(doc_ref.page_range)

            for chunk in doc_chunks:
                chunk_pages = PageRange(start=chunk.page_start, end=chunk.page_end)
                has_exact_match = False

                if ref_pages is not None:
                    # M6-08: Exact page range matching
                    has_exact_match = page_range_matches(ref_pages, chunk_pages)

                # M6-10: Compute semantic similarity
                similarity = compute_text_similarity(sentence, chunk.content)

                # M6-11: Determine confidence
                confidence = determine_confidence(
                    has_exact_page_match=has_exact_match,
                    similarity=similarity,
                    threshold=self._threshold,
                )

                if confidence != "uncertain":
                    matched_chunks.append(
                        MatchedChunk(
                            chunk_id=chunk.chunk_id,
                            document_id=chunk.document_id,
                            page_start=chunk.page_start,
                            page_end=chunk.page_end,
                            excerpt=chunk.content[:200],
                            similarity=round(similarity, 4),
                        )
                    )
                    # Best confidence: direct > fuzzy > uncertain
                    if confidence == "direct":
                        best_confidence = "direct"
                    elif confidence == "fuzzy" and best_confidence != "direct":
                        best_confidence = "fuzzy"

        # Build ref_id string
        if ref.doc_refs:
            ref_id_parts = [
                f"{dr.doc_id}:{dr.page_range}" for dr in ref.doc_refs
            ]
            ref_id = "|".join(ref_id_parts)
        else:
            ref_id = ref.raw_mark

        return VerifiedCitation(
            ref_id=ref_id,
            sentence=sentence,
            sentence_index=sentence_index,
            confidence=best_confidence,
            matched_chunks=matched_chunks,
        )

    def _build_summary(self, citations: list[VerifiedCitation]) -> VerificationSummary:
        """M6-13: Build a summary of verification results (total/direct/fuzzy/uncertain)."""
        total = len(citations)
        direct = sum(1 for c in citations if c.confidence == "direct")
        fuzzy = sum(1 for c in citations if c.confidence == "fuzzy")
        uncertain = sum(1 for c in citations if c.confidence == "uncertain")
        return VerificationSummary(
            total=total, direct=direct, fuzzy=fuzzy, uncertain=uncertain
        )
