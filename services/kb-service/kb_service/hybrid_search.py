"""Hybrid search: vector + BM25 → RRF fusion → reranker → results."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from kb_service.bm25 import BM25Searcher, InMemoryBM25Searcher
from kb_service.config import settings
from kb_service.embedding import EmbeddingClient, MockEmbeddingClient
from kb_service.reranker import NoopReranker, Reranker
from kb_service.vector_store import VectorStore

logger = logging.getLogger(__name__)


class HybridSearcher:
    """Orchestrates hybrid search combining vector semantic + BM25 keyword search.

    Pipeline:
      1. Parallel: vector_search(top_k=50) + BM25_search(top_k=50)
      2. RRF fusion (k=60) → top_k=30
      3. (Optional) BGE-Reranker cross-encoder rescoring
      4. Return top_k results
    """

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        embedding_client: EmbeddingClient | MockEmbeddingClient | None = None,
        bm25_searcher: BM25Searcher | InMemoryBM25Searcher | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        if vector_store is None:
            raise ValueError("vector_store is required")
        if embedding_client is None:
            raise ValueError("embedding_client is required")
        self.vector_store = vector_store
        self.embedding_client = embedding_client
        self.bm25 = bm25_searcher
        self.reranker = reranker or (Reranker() if settings.reranker_enabled else NoopReranker())
        self.rrf_k = settings.hybrid_rrf_k
        self.vector_top_k = settings.hybrid_vector_top_k
        self.bm25_top_k = settings.hybrid_bm25_top_k
        self.merged_top_k = settings.hybrid_merged_top_k
        self.default_top_k = settings.search_default_top_k
        self.timeout_ms = settings.search_timeout_ms

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        project_id: str | None = None,
        document_ids: list[str] | None = None,
        chunk_types: list[str] | None = None,
        search_mode: str = "hybrid",
    ) -> tuple[list[dict[str, Any]], int, float]:
        """Execute hybrid search.

        Returns:
            Tuple of (results, total_hits, search_time_ms).
        """
        start = time.monotonic()
        final_top_k = top_k or self.default_top_k

        # Generate query embedding
        query_vector = await self.embedding_client.embed_single(query)

        # Build vector search filters
        vector_filters: dict[str, Any] = {}
        if project_id:
            vector_filters["project_id"] = project_id
        if document_ids:
            vector_filters["document_ids"] = document_ids

        if search_mode == "vector":
            # Vector-only search
            vec_results = await self._vector_search_with_timeout(query_vector, self.vector_top_k, vector_filters)
            elapsed_ms = (time.monotonic() - start) * 1000
            return vec_results[:final_top_k], len(vec_results), elapsed_ms

        if search_mode == "bm25":
            # BM25-only search
            bm25_results = await self._bm25_search_with_timeout(
                query, self.bm25_top_k, project_id, document_ids, chunk_types
            )
            elapsed_ms = (time.monotonic() - start) * 1000
            return bm25_results[:final_top_k], len(bm25_results), elapsed_ms

        # Hybrid: parallel vector + BM25 → RRF fusion
        vec_results, bm25_results = await asyncio.gather(
            self._vector_search_with_timeout(query_vector, self.vector_top_k, vector_filters),
            self._bm25_search_with_timeout(query, self.bm25_top_k, project_id, document_ids, chunk_types),
        )

        # RRF fusion
        fused = self._rrf_fusion(vec_results, bm25_results, self.rrf_k)[: self.merged_top_k]

        # Reranker (optional - when enabled and configured)
        if settings.reranker_enabled:
            fused = await self.reranker.rerank(query, fused)

        elapsed_ms = (time.monotonic() - start) * 1000
        return fused[:final_top_k], len(vec_results) + len(bm25_results), elapsed_ms

    async def _vector_search_with_timeout(
        self,
        query_vector: list[float],
        top_k: int,
        filters: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        try:
            results = await asyncio.wait_for(
                self.vector_store.search(query_vector, top_k=top_k, filters=filters),
                timeout=self.timeout_ms / 1000.0,
            )
            return [
                {
                    "chunk_id": r["chunk_id"],
                    "document_id": r.get("metadata", {}).get("document_id", ""),
                    "chunk_type": r.get("metadata", {}).get("chunk_type", ""),
                    "content": r.get("metadata", {}).get("content", ""),
                    "score": r["score"],
                    "document_title": "",
                    "document_filename": "",
                    "metadata": r.get("metadata", {}),
                }
                for r in results
            ]
        except TimeoutError:
            logger.warning("Vector search timed out after %dms", self.timeout_ms)
            return []

    async def _bm25_search_with_timeout(
        self,
        query: str,
        top_k: int,
        project_id: str | None,
        document_ids: list[str] | None,
        chunk_types: list[str] | None,
    ) -> list[dict[str, Any]]:
        try:
            if self.bm25 is None:
                return []

            results = await asyncio.wait_for(
                self.bm25.search(
                    query=query,
                    top_k=top_k,
                    project_id=project_id,
                    document_ids=document_ids,
                    chunk_types=chunk_types,
                ),
                timeout=self.timeout_ms / 1000.0,
            )
            return [
                {
                    "chunk_id": r["chunk_id"],
                    "document_id": r.get("document_id", ""),
                    "chunk_type": r.get("chunk_type", ""),
                    "content": r.get("content", ""),
                    "score": r["score"],
                    "document_title": r.get("document_title", ""),
                    "document_filename": r.get("document_filename", ""),
                    "metadata": {
                        "document_id": r.get("document_id", ""),
                        "chunk_type": r.get("chunk_type", ""),
                        "page_start": r.get("page_start", 0),
                        "page_end": r.get("page_end", 0),
                    },
                }
                for r in results
            ]
        except TimeoutError:
            logger.warning("BM25 search timed out after %dms", self.timeout_ms)
            return []

    @staticmethod
    def _rrf_fusion(
        vec_results: list[dict[str, Any]],
        bm25_results: list[dict[str, Any]],
        k: int = 60,
    ) -> list[dict[str, Any]]:
        """Reciprocal Rank Fusion: score = SUM(1 / (k + rank)) for each result list.

        Higher rank (lower rank number) = higher contribution to final score.
        """
        scores: dict[str, float] = {}
        merged: dict[str, dict[str, Any]] = {}

        for rank, result in enumerate(vec_results, start=1):
            cid = result["chunk_id"]
            rrf_score = 1.0 / (k + rank)
            scores[cid] = scores.get(cid, 0.0) + rrf_score
            if cid not in merged:
                merged[cid] = dict(result)

        for rank, result in enumerate(bm25_results, start=1):
            cid = result["chunk_id"]
            rrf_score = 1.0 / (k + rank)
            scores[cid] = scores.get(cid, 0.0) + rrf_score
            if cid not in merged:
                merged[cid] = dict(result)

        # Sort by combined RRF score
        sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
        for cid in sorted_ids:
            merged[cid]["score"] = scores[cid]

        return [merged[cid] for cid in sorted_ids]
