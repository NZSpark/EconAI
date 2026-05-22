"""FastAPI application for the Citation Service (M6-14 through M6-18).

Endpoints:
  - GET  /health                                             Health check
  - POST /internal/citations/verify                          Verify citations (M6-14, M6-15)
  - GET  /api/tasks/{task_id}/output/citations               List citations (M6-16)
  - GET  /api/tasks/{task_id}/output/citations/{citation_id} Citation detail (M6-17, M6-18)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from shared.models import ErrorResponse

from citation_service.config import config as cfg
from citation_service.formatter import (
    CitationFormatter,
)
from citation_service.parser import CitationParser
from citation_service.verifier import (
    CitationVerifier,
    ContextChunk,
    VerificationResult,
    VerifiedCitation,
)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="EconAI Citation Service",
    version="0.1.0",
    description="Inline citation parsing, verification, and formatting (M6).",
)

# ---------------------------------------------------------------------------
# Service instances
# ---------------------------------------------------------------------------

parser = CitationParser()
verifier = CitationVerifier(similarity_threshold=cfg.CITATION_SIMILARITY_THRESHOLD)
formatter = CitationFormatter()

# ---------------------------------------------------------------------------
# In-memory storage for citations (MVP, no DB dependency for tests)
# ---------------------------------------------------------------------------

# task_id -> list[dict] mapping for query endpoints
_citation_store: dict[str, list[dict[str, Any]]] = {}


# Pydantic models for request/response
# ---------------------------------------------------------------------------


class ContextChunkRequest(BaseModel):
    """Context chunk provided in request body (since no KB service yet)."""

    chunk_id: str
    document_id: str
    content: str
    page_start: int
    page_end: int


class VerifyRequest(BaseModel):
    """M6-14: Request body for POST /internal/citations/verify."""

    text: str = Field(..., description="LLM output text containing [ref:...] markers")
    context_chunks: list[ContextChunkRequest] = Field(
        default_factory=list,
        description="Context chunks for verification",
    )


class MatchedChunkResponse(BaseModel):
    """M6-15: Matched chunk detail in verification response."""

    chunk_id: str
    document_id: str
    page_start: int
    page_end: int
    excerpt: str
    similarity: float


class VerifiedCitationResponse(BaseModel):
    """Verified citation in API response."""

    ref_id: str
    sentence: str
    sentence_index: int
    confidence: str
    matched_chunks: list[MatchedChunkResponse]


class VerificationSummaryResponse(BaseModel):
    """Summary of verification results."""

    total: int
    direct: int
    fuzzy: int
    uncertain: int


class VerifyResponse(BaseModel):
    """M6-14/M6-15: Response for POST /internal/citations/verify."""

    citations: list[VerifiedCitationResponse]
    summary: VerificationSummaryResponse


class CitationDetailSource(BaseModel):
    """M6-18: Source detail for a single citation."""

    document_id: str
    page_start: int | None = None
    page_end: int | None = None
    excerpt: str | None = None


class CitationDetailResponse(BaseModel):
    """M6-17/M6-18: Single citation detail response."""

    ref_id: str
    sentence: str
    confidence: str
    source: CitationDetailSource | None = None
    verified_at: datetime | None = None
    verified_by: str | None = None


# ErrorDetail, ErrorResponse — imported from shared.models


# ---------------------------------------------------------------------------
# Helper to convert verification result to response
# ---------------------------------------------------------------------------


def _to_verified_response(vc: VerifiedCitation) -> VerifiedCitationResponse:
    """Convert internal VerifiedCitation to API response model."""
    return VerifiedCitationResponse(
        ref_id=vc.ref_id,
        sentence=vc.sentence,
        sentence_index=vc.sentence_index,
        confidence=vc.confidence,
        matched_chunks=[
            MatchedChunkResponse(
                chunk_id=mc.chunk_id,
                document_id=mc.document_id,
                page_start=mc.page_start,
                page_end=mc.page_end,
                excerpt=mc.excerpt,
                similarity=mc.similarity,
            )
            for mc in vc.matched_chunks
        ],
    )


def _verification_result_to_citations(result: VerificationResult) -> list[dict[str, Any]]:
    """Convert VerificationResult to storable citation dicts for in-memory store."""
    now = datetime.now(UTC)
    records: list[dict[str, Any]] = []
    for vc in result.citations:
        records.append(
            {
                "id": str(uuid.uuid4()),
                "ref_id": vc.ref_id,
                "sentence": vc.sentence,
                "sentence_index": vc.sentence_index,
                "confidence": vc.confidence,
                "matched_chunks": [
                    {
                        "chunk_id": mc.chunk_id,
                        "document_id": mc.document_id,
                        "page_start": mc.page_start,
                        "page_end": mc.page_end,
                        "excerpt": mc.excerpt,
                        "similarity": mc.similarity,
                    }
                    for mc in vc.matched_chunks
                ],
                "verified_at": now.isoformat(),
                "verified_by": cfg.SERVICE_NAME,
            }
        )
    return records


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, object]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": cfg.SERVICE_NAME,
        "config": {
            "similarity_threshold": cfg.CITATION_SIMILARITY_THRESHOLD,
            "verify_batch_size": cfg.CITATION_VERIFY_BATCH_SIZE,
            "format": "footnote" if cfg.CITATION_FORMAT_FOOTNOTE else "endnote",
        },
    }


# ---------------------------------------------------------------------------
# M6-14/M6-15: Verify citations
# ---------------------------------------------------------------------------


@app.post(
    "/internal/citations/verify",
    response_model=VerifyResponse,
    responses={400: {"model": ErrorResponse}},
)
async def verify_citations(request: VerifyRequest) -> VerifyResponse:
    """Verify inline citations in LLM output text.

    Accepts text + context_chunks, runs parsing + verification,
    and returns verified citations with matched chunk details.
    """
    if not request.text.strip():
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "EMPTY_TEXT", "message": "Text must not be empty."}},
        )

    # Step 1: Parse inline citations
    parser_result = parser.parse(request.text)

    # Step 2: Convert request chunks to ContextChunk domain objects
    context_chunks = [
        ContextChunk(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            content=chunk.content,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
        )
        for chunk in request.context_chunks
    ]

    # Step 3: Verify
    verify_result = verifier.verify(parser_result, context_chunks)

    # Step 4: Convert to response
    citations = [_to_verified_response(vc) for vc in verify_result.citations]
    summary = VerificationSummaryResponse(
        total=verify_result.summary.total,
        direct=verify_result.summary.direct,
        fuzzy=verify_result.summary.fuzzy,
        uncertain=verify_result.summary.uncertain,
    )

    return VerifyResponse(citations=citations, summary=summary)


# ---------------------------------------------------------------------------
# M6-16: List citations for a task output
# ---------------------------------------------------------------------------


@app.get(
    "/api/tasks/{task_id}/output/citations",
    response_model=list[VerifiedCitationResponse],
)
async def list_citations(
    task_id: str,
    confidence: Annotated[str | None, Query(description="Filter by confidence level")] = None,
) -> list[VerifiedCitationResponse]:
    """List verified citations for a task output.

    Optionally filter by confidence level (direct/fuzzy/uncertain).
    """
    records = _citation_store.get(task_id, [])

    if confidence:
        records = [r for r in records if r["confidence"] == confidence]

    return [
        VerifiedCitationResponse(
            ref_id=r["ref_id"],
            sentence=r["sentence"],
            sentence_index=r["sentence_index"],
            confidence=r["confidence"],
            matched_chunks=[
                MatchedChunkResponse(**mc) for mc in r.get("matched_chunks", [])
            ],
        )
        for r in records
    ]


# ---------------------------------------------------------------------------
# M6-17/M6-18: Single citation detail
# ---------------------------------------------------------------------------


@app.get(
    "/api/tasks/{task_id}/output/citations/{citation_id}",
    response_model=CitationDetailResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_citation_detail(
    task_id: str,
    citation_id: str,
) -> CitationDetailResponse:
    """Get a single citation detail including source information.

    Returns: ref_id, sentence, confidence, source (document_id, pages, excerpt),
             verified_at, verified_by.
    """
    records = _citation_store.get(task_id, [])

    # Find the citation by id
    found: dict[str, Any] | None = None
    for r in records:
        if r["id"] == citation_id:
            found = r
            break

    if found is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "NOT_FOUND",
                    "message": f"Citation {citation_id} not found for task {task_id}.",
                }
            },
        )

    # Build source from first matched chunk
    source = None
    matched = found.get("matched_chunks", [])
    if matched:
        first = matched[0]
        source = CitationDetailSource(
            document_id=first["document_id"],
            page_start=first.get("page_start"),
            page_end=first.get("page_end"),
            excerpt=first.get("excerpt"),
        )

    verified_at = None
    if found.get("verified_at"):
        verified_at = datetime.fromisoformat(found["verified_at"])

    return CitationDetailResponse(
        ref_id=found["ref_id"],
        sentence=found["sentence"],
        confidence=found["confidence"],
        source=source,
        verified_at=verified_at,
        verified_by=found.get("verified_by"),
    )


# ---------------------------------------------------------------------------
# Internal helpers (exposed for test usage via direct import)
# ---------------------------------------------------------------------------


def _store_verification_result(task_id: str, result: VerificationResult) -> list[dict[str, Any]]:
    """Store a verification result in the in-memory cache and return records.

    This is an internal function used by upstream services to persist results
    after verify for later query endpoints.
    """
    records = _verification_result_to_citations(result)
    _citation_store[task_id] = records
    return records
