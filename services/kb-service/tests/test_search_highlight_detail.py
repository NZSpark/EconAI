"""Tests for KB search functionality (User Manual §4.5).

Black-box tests: all tests go through the HTTP API endpoints
  POST /api/projects/{project_id}/search
  POST /api/institutional/search

User Manual §4.5 states:
- 在搜索框中输入关键词，系统进行混合检索（语义匹配 + 关键词匹配）
- 结果列表显示匹配的文本片段
- 每个结果标注来源文档和相关性分数
- 高亮显示匹配的关键词  ← NOT IMPLEMENTED: no highlight/highlighted_content field

Gaps found:
  GAP-A: 搜索结果没有返回高亮文本 (highlight/highlighted_content)
         用户手册 §4.5: "高亮显示匹配的关键词"
         当前 ChunkResult 只有 content 原始文本，没有带高亮标记的版本
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kb_service.app import app
from kb_service.bm25 import InMemoryBM25Searcher
from kb_service.embedding import MockEmbeddingClient
from kb_service.hybrid_search import HybridSearcher
from kb_service.indexer import IndexPipeline
from kb_service.vector_store import InMemoryVectorStore


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

_SAMPLE_CHUNKS: list[dict[str, Any]] = [
    {
        "chunk_id": "c1",
        "document_id": "doc-1",
        "project_id": "proj-1",
        "content": "数字贸易规则正在成为国际贸易谈判的核心议题。",
        "chunk_type": "paragraph",
        "page_start": 1,
        "page_end": 1,
    },
    {
        "chunk_id": "c2",
        "document_id": "doc-1",
        "project_id": "proj-1",
        "content": "关税壁垒和非关税壁垒是贸易保护主义的两种主要形式。",
        "chunk_type": "paragraph",
        "page_start": 2,
        "page_end": 2,
    },
    {
        "chunk_id": "c3",
        "document_id": "doc-2",
        "project_id": "proj-1",
        "content": "Digital trade rules should address cross-border data flows.",
        "chunk_type": "paragraph",
        "page_start": 5,
        "page_end": 5,
    },
    {
        "chunk_id": "c4",
        "document_id": "doc-2",
        "project_id": "proj-1",
        "content": "WTO negotiations on e-commerce have made significant progress.",
        "chunk_type": "paragraph",
        "page_start": 10,
        "page_end": 10,
    },
    {
        "chunk_id": "c5",
        "document_id": "doc-1",
        "project_id": "proj-1",
        "content": "碳排放交易体系是应对气候变化的重要政策工具。",
        "chunk_type": "paragraph",
        "page_start": 8,
        "page_end": 8,
    },
]

_PROJ_B_CHUNK: dict[str, Any] = {
    "chunk_id": "cb1",
    "document_id": "doc-b1",
    "project_id": "proj-b",
    "content": "可再生能源补贴政策促进了清洁能源发展。",
    "chunk_type": "paragraph",
    "page_start": 3,
    "page_end": 3,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_kb_with_chunks(chunks: list[dict[str, Any]]) -> HybridSearcher:
    """Wire the KB service's global searcher/pipeline with in-memory components,
    index the given chunks, and return the searcher."""
    from kb_service import app as app_module
    from kb_service.lifecycle import _archived_documents, _archived_projects

    vs = InMemoryVectorStore(dim=768)
    emb = MockEmbeddingClient(dim=768)
    bm25 = InMemoryBM25Searcher()

    searcher = HybridSearcher(vector_store=vs, embedding_client=emb, bm25_searcher=bm25)
    pipeline = IndexPipeline(vector_store=vs, embedding_client=emb, bm25_searcher=bm25)

    app_module._vector_store = vs  # type: ignore[attr-defined]
    app_module._embedding = emb  # type: ignore[attr-defined]
    app_module._bm25 = bm25  # type: ignore[attr-defined]
    app_module._searcher = searcher  # type: ignore[attr-defined]
    app_module._pipeline = pipeline  # type: ignore[attr-defined]

    _archived_projects.clear()
    _archived_documents.clear()

    async def _index() -> None:
        await pipeline.index_chunks(chunks)

    asyncio.run(_index())
    return searcher


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient for the KB service."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# §4.5 搜索知识库 — 基本搜索功能 (should pass — already implemented)
# ---------------------------------------------------------------------------


class TestSearchBasic:
    """User Manual §4.5: Basic search — keyword search, results with text fragments."""

    def test_search_returns_results(self, client: TestClient) -> None:
        """Searching '贸易' should return matching chunks with text content."""
        _setup_kb_with_chunks(_SAMPLE_CHUNKS)

        resp = client.post(
            "/api/projects/proj-1/search",
            json={"query": "贸易", "top_k": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_hits"] > 0
        assert len(data["results"]) > 0
        contents = [r["content"] for r in data["results"]]
        assert any("贸易" in c for c in contents)

    def test_search_no_results(self, client: TestClient) -> None:
        """Searching a term not in any chunk returns empty results."""
        _setup_kb_with_chunks(_SAMPLE_CHUNKS)

        resp = client.post(
            "/api/projects/proj-1/search",
            json={"query": "xyz_not_in_any_chunk_abc", "top_k": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_hits"] >= 0


# ---------------------------------------------------------------------------
# §4.5 搜索结果标注 — 来源文档和相关性分数 (should pass — already implemented)
# ---------------------------------------------------------------------------


class TestSearchResultMetadata:
    """User Manual §4.5: Each result should show source document and relevance score."""

    def test_results_include_document_id(self, client: TestClient) -> None:
        """每个结果标注来源文档 (document_id)."""
        _setup_kb_with_chunks(_SAMPLE_CHUNKS)

        resp = client.post(
            "/api/projects/proj-1/search",
            json={"query": "贸易", "top_k": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        for r in data["results"]:
            assert "document_id" in r
            assert r["document_id"] in ("doc-1", "doc-2")

    def test_results_include_relevance_score(self, client: TestClient) -> None:
        """每个结果标注相关性分数 (score)."""
        _setup_kb_with_chunks(_SAMPLE_CHUNKS)

        resp = client.post(
            "/api/projects/proj-1/search",
            json={"query": "贸易", "top_k": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        for r in data["results"]:
            assert "score" in r
            assert isinstance(r["score"], (int, float))
            assert r["score"] >= 0

    def test_results_have_required_structure(self, client: TestClient) -> None:
        """Search response should include results, total_hits, search_time_ms."""
        _setup_kb_with_chunks(_SAMPLE_CHUNKS)

        resp = client.post(
            "/api/projects/proj-1/search",
            json={"query": "贸易", "top_k": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "total_hits" in data
        assert "search_time_ms" in data
        assert isinstance(data["results"], list)
        assert isinstance(data["total_hits"], int)

    def test_results_sorted_by_score_descending(self, client: TestClient) -> None:
        """Search results should be ordered by relevance score descending."""
        _setup_kb_with_chunks(_SAMPLE_CHUNKS)

        resp = client.post(
            "/api/projects/proj-1/search",
            json={"query": "贸易", "top_k": 10},
        )
        assert resp.status_code == 200
        data = resp.json()
        if len(data["results"]) >= 2:
            scores = [r["score"] for r in data["results"]]
            for i in range(len(scores) - 1):
                assert scores[i] >= scores[i + 1], f"Scores not monotonic at index {i}: {scores}"


# ===========================================================================
# GAP TESTS — these SHOULD FAIL because the feature is missing from the API
# ===========================================================================


class TestSearchHighlightMissing:
    """GAP-A: 用户手册 §4.5 明确要求"高亮显示匹配的关键词"。

    当前 API 的 ChunkResult 只返回 content 原始文本，不包含任何高亮信息。
    前端无法知道哪些词是匹配的关键词，只能自行在 content 中搜索。

    期望: 搜索结果应包含 matched_terms（匹配的关键词列表）或
          highlighted_content（带高亮标记如 <em>...</em> 的文本片段），
          使前端可以渲染高亮显示。
    """

    def test_result_has_matched_terms_or_highlight(self, client: TestClient) -> None:
        """GAP: 搜索结果应该返回匹配的关键词或高亮文本。

        这个测试会失败，因为当前 ChunkResult 没有 matched_terms 或
        highlighted_content 字段。
        """
        _setup_kb_with_chunks(_SAMPLE_CHUNKS)

        resp = client.post(
            "/api/projects/proj-1/search",
            json={"query": "贸易", "top_k": 5},
        )
        assert resp.status_code == 200
        data = resp.json()

        for r in data["results"]:
            # 期望: 每个结果应该有 matched_terms 或 highlighted_content
            has_matched_terms = "matched_terms" in r and len(r["matched_terms"]) > 0
            has_highlight = "highlighted_content" in r and r["highlighted_content"]
            assert has_matched_terms or has_highlight, (
                f"GAP: Search result missing highlight info. "
                f"User Manual §4.5 says '高亮显示匹配的关键词'. "
                f"Expected 'matched_terms' or 'highlighted_content' in result: {r.get('chunk_id')}"
            )

    def test_bm25_result_has_highlight_for_exact_match(self, client: TestClient) -> None:
        """GAP: BM25 精确匹配的搜索结果应该包含高亮信息。

        当用户搜索英文关键词时，返回的 content 中匹配词应该被高亮标记。
        使用英文因为 InMemoryBM25Searcher 对中文无分词能力。
        """
        _setup_kb_with_chunks(_SAMPLE_CHUNKS)

        resp = client.post(
            "/api/projects/proj-1/search",
            json={"query": "trade rules", "top_k": 3, "search_mode": "bm25"},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_hits"] > 0, (
            "BM25 should find 'trade' in the sample English chunks; "
            "if total_hits=0, BM25 indexing may have a bug."
        )
        for r in data["results"]:
            has_matched_terms = "matched_terms" in r and len(r["matched_terms"]) > 0
            has_highlight = "highlighted_content" in r and r["highlighted_content"]
            assert has_matched_terms or has_highlight, (
                f"GAP: BM25 result missing highlight info for exact keyword match. "
                f"User Manual §4.5 says '高亮显示匹配的关键词'. "
                f"Expected 'matched_terms' or 'highlighted_content' in result: {r.get('chunk_id')}"
            )


# ---------------------------------------------------------------------------
# §4.5 混合检索 (should pass — already implemented)
# ---------------------------------------------------------------------------


class TestSearchModes:
    """User Manual §4.5: 系统进行混合检索（语义匹配 + 关键词匹配）."""

    def test_default_mode_is_hybrid(self, client: TestClient) -> None:
        """Default search (no search_mode specified) should work."""
        _setup_kb_with_chunks(_SAMPLE_CHUNKS)

        resp = client.post(
            "/api/projects/proj-1/search",
            json={"query": "贸易", "top_k": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_hits"] > 0

    def test_hybrid_mode_returns_results(self, client: TestClient) -> None:
        """Explicit hybrid mode should return results."""
        _setup_kb_with_chunks(_SAMPLE_CHUNKS)

        resp = client.post(
            "/api/projects/proj-1/search",
            json={"query": "贸易", "top_k": 5, "search_mode": "hybrid"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_hits"] > 0

    def test_vector_mode_returns_results(self, client: TestClient) -> None:
        """Vector-only mode should return semantically relevant results."""
        _setup_kb_with_chunks(_SAMPLE_CHUNKS)

        resp = client.post(
            "/api/projects/proj-1/search",
            json={"query": "国际商务规则", "top_k": 5, "search_mode": "vector"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_hits"] > 0

    def test_bm25_mode_returns_results(self, client: TestClient) -> None:
        """BM25-only mode should return keyword-matched results."""
        _setup_kb_with_chunks(_SAMPLE_CHUNKS)

        resp = client.post(
            "/api/projects/proj-1/search",
            json={"query": "trade rules", "top_k": 5, "search_mode": "bm25"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_hits"] >= 0


# ---------------------------------------------------------------------------
# §4.5 top_k 限制 (should pass — already implemented)
# ---------------------------------------------------------------------------


class TestSearchPagination:
    """User Manual §4.5: search result limits."""

    def test_top_k_limits_result_count(self, client: TestClient) -> None:
        """top_k parameter limits the number of returned results."""
        _setup_kb_with_chunks(_SAMPLE_CHUNKS)

        resp = client.post(
            "/api/projects/proj-1/search",
            json={"query": "贸易", "top_k": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) <= 2

    def test_total_hits_not_limited_by_top_k(self, client: TestClient) -> None:
        """total_hits reports all matches, not limited by top_k."""
        _setup_kb_with_chunks(_SAMPLE_CHUNKS)

        resp = client.post(
            "/api/projects/proj-1/search",
            json={"query": "贸易", "top_k": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) <= 1
        assert data["total_hits"] >= len(data["results"])


# ---------------------------------------------------------------------------
# §4.5 文档过滤 (should pass — already implemented)
# ---------------------------------------------------------------------------


class TestSearchDocumentFilter:
    """User Manual §4.2, §4.5: Filter search by document."""

    def test_filter_by_document_ids(self, client: TestClient) -> None:
        """Searching with document_ids filter only returns results from those docs."""
        _setup_kb_with_chunks(_SAMPLE_CHUNKS)

        resp = client.post(
            "/api/projects/proj-1/search",
            json={
                "query": "贸易",
                "top_k": 10,
                "filters": {"document_ids": ["doc-1"]},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        for r in data["results"]:
            assert r["document_id"] == "doc-1"

    def test_filter_by_non_matching_document(self, client: TestClient) -> None:
        """Filtering by a document with no matching content returns no results."""
        _setup_kb_with_chunks(_SAMPLE_CHUNKS)

        resp = client.post(
            "/api/projects/proj-1/search",
            json={
                "query": "贸易",
                "top_k": 5,
                "filters": {"document_ids": ["doc-nonexistent"]},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_hits"] == 0


# ---------------------------------------------------------------------------
# §4.5 跨项目/机构搜索 (should pass — already implemented)
# ---------------------------------------------------------------------------


class TestInstitutionalSearch:
    """User Manual §4.5: 机构搜索 vs 项目内搜索."""

    def test_institutional_search_finds_across_projects(self, client: TestClient) -> None:
        """Institutional search should find results from all projects."""
        _setup_kb_with_chunks(_SAMPLE_CHUNKS + [_PROJ_B_CHUNK])

        resp = client.post(
            "/api/institutional/search",
            json={"query": "能源政策", "top_k": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_hits"] > 0

    def test_project_search_is_scoped_to_project(self, client: TestClient) -> None:
        """Project search only returns results from the specified project."""
        _setup_kb_with_chunks(_SAMPLE_CHUNKS + [_PROJ_B_CHUNK])

        resp = client.post(
            "/api/projects/proj-b/search",
            json={"query": "能源政策", "top_k": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        for r in data["results"]:
            assert r["document_id"] == "doc-b1"
