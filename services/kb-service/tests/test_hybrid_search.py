"""End-to-end hybrid search tests — vector + BM25 complementarity (M3-33)."""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio

from kb_service.bm25 import InMemoryBM25Searcher
from kb_service.embedding import MockEmbeddingClient
from kb_service.hybrid_search import HybridSearcher
from kb_service.indexer import IndexPipeline
from kb_service.vector_store import InMemoryVectorStore


def _make_chunks(project_id: str = "proj-1", count: int = 10, prefix: str = "chunk") -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for i in range(count):
        chunks.append({
            "chunk_id": f"{prefix}-{i}",
            "document_id": f"doc-{i % 3}",
            "project_id": project_id,
            "content": f"This is {prefix} number {i} about economic policy analysis and trade regulation",
            "chunk_type": "paragraph",
            "page_start": i,
            "page_end": i,
        })
    return chunks


@pytest_asyncio.fixture
async def indexed_searcher() -> HybridSearcher:
    vs = InMemoryVectorStore(dim=768)
    emb = MockEmbeddingClient(dim=768)
    bm25 = InMemoryBM25Searcher()
    searcher = HybridSearcher(vector_store=vs, embedding_client=emb, bm25_searcher=bm25)
    chunks = _make_chunks("proj-1", count=20)
    pipeline = IndexPipeline(vector_store=vs, embedding_client=emb, bm25_searcher=bm25)
    await pipeline.index_chunks(chunks)
    return searcher


@pytest_asyncio.fixture
async def empty_searcher() -> HybridSearcher:
    vs = InMemoryVectorStore(dim=768)
    emb = MockEmbeddingClient(dim=768)
    bm25 = InMemoryBM25Searcher()
    return HybridSearcher(vector_store=vs, embedding_client=emb, bm25_searcher=bm25)


class TestHybridSearch:
    @pytest.mark.asyncio
    async def test_hybrid_search_returns_results(self, indexed_searcher: HybridSearcher) -> None:
        results, total_hits, elapsed = await indexed_searcher.search(
            query="economic policy", top_k=5, project_id="proj-1"
        )
        assert len(results) <= 5
        assert total_hits > 0
        assert elapsed >= 0

    @pytest.mark.asyncio
    async def test_vector_only_mode(self, indexed_searcher: HybridSearcher) -> None:
        results, total, _ = await indexed_searcher.search(
            query="trade regulation", top_k=3, project_id="proj-1", search_mode="vector"
        )
        assert len(results) <= 3
        assert total >= 0

    @pytest.mark.asyncio
    async def test_bm25_only_mode(self, indexed_searcher: HybridSearcher) -> None:
        results, total, _ = await indexed_searcher.search(
            query="trade regulation", top_k=3, project_id="proj-1", search_mode="bm25"
        )
        assert len(results) <= 3
        assert total >= 0

    @pytest.mark.asyncio
    async def test_different_project_returns_empty(self, indexed_searcher: HybridSearcher) -> None:
        results, _, _ = await indexed_searcher.search(query="economic policy", top_k=5, project_id="proj-other")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_scores_are_monotonic(self, indexed_searcher: HybridSearcher) -> None:
        results, _, _ = await indexed_searcher.search(query="economic policy", top_k=10, project_id="proj-1")
        scores = [r["score"] for r in results]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]

    @pytest.mark.asyncio
    async def test_empty_index_returns_no_results(self, empty_searcher: HybridSearcher) -> None:
        results, total, _ = await empty_searcher.search(query="anything", project_id="proj-1")
        assert len(results) == 0
        assert total == 0

    @pytest.mark.asyncio
    async def test_search_document_id_filter(self, indexed_searcher: HybridSearcher) -> None:
        results, _, _ = await indexed_searcher.search(
            query="economic policy", top_k=10, project_id="proj-1", document_ids=["doc-0"]
        )
        for r in results:
            assert r["document_id"] == "doc-0"

    @pytest.mark.asyncio
    async def test_search_chunk_type_filter(self, indexed_searcher: HybridSearcher) -> None:
        results, _, _ = await indexed_searcher.search(
            query="economic", top_k=10, project_id="proj-1", chunk_types=["paragraph"]
        )
        for r in results:
            assert r["chunk_type"] == "paragraph"

    @pytest.mark.asyncio
    async def test_vector_bm25_complementarity(self, indexed_searcher: HybridSearcher) -> None:
        query = "trade regulation analysis"
        vec_results, _, _ = await indexed_searcher.search(
            query=query, top_k=10, project_id="proj-1", search_mode="vector"
        )
        bm25_results, _, _ = await indexed_searcher.search(
            query=query, top_k=10, project_id="proj-1", search_mode="bm25"
        )
        hybrid_results, _, _ = await indexed_searcher.search(
            query=query, top_k=10, project_id="proj-1", search_mode="hybrid"
        )

        vec_ids = {r["chunk_id"] for r in vec_results}
        bm25_ids = {r["chunk_id"] for r in bm25_results}
        hybrid_ids = {r["chunk_id"] for r in hybrid_results}

        assert len(hybrid_ids) >= min(len(vec_ids), len(bm25_ids))

    @pytest.mark.asyncio
    async def test_result_format_has_required_fields(self, indexed_searcher: HybridSearcher) -> None:
        results, _, _ = await indexed_searcher.search(query="policy", top_k=1, project_id="proj-1")
        if results:
            r = results[0]
            assert "chunk_id" in r
            assert "document_id" in r
            assert "content" in r
            assert "chunk_type" in r
            assert "score" in r
            assert "metadata" in r
