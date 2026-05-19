"""Tests for knowledge base isolation and permission checks (M3-34)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kb_service.app import app
from kb_service.bm25 import InMemoryBM25Searcher
from kb_service.embedding import MockEmbeddingClient
from kb_service.hybrid_search import HybridSearcher
from kb_service.indexer import IndexPipeline
from kb_service.lifecycle import LifecycleManager, _archived_documents, _archived_projects
from kb_service.vector_store import InMemoryVectorStore


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _setup_isolation_test_data() -> None:
    """Set up test data with different project ownership."""
    from kb_service import app as app_module

    vs = InMemoryVectorStore(dim=768)
    emb = MockEmbeddingClient(dim=768)
    bm25 = InMemoryBM25Searcher()

    app_module._vector_store = vs
    app_module._embedding = emb
    app_module._bm25 = bm25
    app_module._searcher = HybridSearcher(vector_store=vs, embedding_client=emb, bm25_searcher=bm25)
    app_module._pipeline = IndexPipeline(vector_store=vs, embedding_client=emb, bm25_searcher=bm25)
    app_module._lifecycle = LifecycleManager(app_module._pipeline)

    _archived_projects.clear()
    _archived_documents.clear()


class TestIsolation:
    """Tests that search results are isolated by project_id."""

    def test_project_a_cannot_see_project_b_data(self, client: TestClient) -> None:
        _setup_isolation_test_data()

        # Index data for project A
        import asyncio

        from kb_service import app as app_module

        async def index_a() -> None:
            await app_module._pipeline.index_chunks([
                {
                    "chunk_id": "a-1",
                    "document_id": "doc-a",
                    "project_id": "proj-a",
                    "content": "secret project alpha economic forecast",
                    "chunk_type": "paragraph",
                    "page_start": 1,
                    "page_end": 1,
                }
            ])

        asyncio.run(index_a())

        # Search project A — should find results
        resp_a = client.post("/api/projects/proj-a/search", json={"query": "economic forecast"})
        assert resp_a.status_code == 200
        assert resp_a.json()["total_hits"] > 0

        # Search project B — should find nothing
        resp_b = client.post("/api/projects/proj-b/search", json={"query": "economic forecast"})
        assert resp_b.status_code == 200
        assert resp_b.json()["total_hits"] == 0

    def test_cross_project_search_sees_all(self, client: TestClient) -> None:
        _setup_isolation_test_data()

        import asyncio

        from kb_service import app as app_module

        async def index_both() -> None:
            await app_module._pipeline.index_chunks([
                {
                    "chunk_id": "x-1",
                    "document_id": "doc-x",
                    "project_id": "proj-x",
                    "content": "institutional knowledge about trade policy",
                    "chunk_type": "paragraph",
                    "page_start": 1,
                    "page_end": 1,
                },
                {
                    "chunk_id": "y-1",
                    "document_id": "doc-y",
                    "project_id": "proj-y",
                    "content": "another institutional resource on fiscal policy",
                    "chunk_type": "paragraph",
                    "page_start": 1,
                    "page_end": 1,
                },
            ])

        asyncio.run(index_both())

        # Institutional search (cross-project) should find both
        resp = client.post("/api/institutional/search", json={"query": "policy"})
        assert resp.status_code == 200
        assert resp.json()["total_hits"] > 0

    def test_archived_project_denied(self, client: TestClient) -> None:
        _setup_isolation_test_data()
        _archived_projects.add("proj-archived")

        resp = client.post("/api/projects/proj-archived/search", json={"query": "test"})
        assert resp.status_code == 403
        assert "archived" in resp.json()["error"]["message"].lower()

    def test_restored_project_allows_search(self, client: TestClient) -> None:
        _setup_isolation_test_data()

        import asyncio

        from kb_service import app as app_module

        async def index() -> None:
            await app_module._pipeline.index_chunks([
                {
                    "chunk_id": "r-1",
                    "document_id": "doc-r",
                    "project_id": "proj-restored",
                    "content": "restored project content about monetary policy",
                    "chunk_type": "paragraph",
                    "page_start": 1,
                    "page_end": 1,
                }
            ])

        asyncio.run(index())

        # Archive then restore
        resp_archive = client.post("/internal/lifecycle/archive/project/proj-restored")
        assert resp_archive.status_code == 200

        resp_restore = client.post("/internal/lifecycle/restore/project/proj-restored")
        assert resp_restore.status_code == 200

        # Should now be searchable again
        from kb_service.lifecycle import _archived_projects
        assert "proj-restored" not in _archived_projects

        resp = client.post("/api/projects/proj-restored/search", json={"query": "monetary policy"})
        assert resp.status_code == 200
        # Results should be findable after restore
        assert resp.json()["total_hits"] > 0

    def test_document_archive_and_restore(self, client: TestClient) -> None:
        _setup_isolation_test_data()
        _archived_documents.clear()

        resp_archive = client.post("/internal/lifecycle/archive/document/doc-test")
        assert resp_archive.status_code == 200
        assert "doc-test" in _archived_documents

        resp_restore = client.post("/internal/lifecycle/restore/document/doc-test")
        assert resp_restore.status_code == 200
        assert "doc-test" not in _archived_documents

    def test_internal_search_with_project_id(self, client: TestClient) -> None:
        _setup_isolation_test_data()

        import asyncio

        from kb_service import app as app_module

        async def index() -> None:
            await app_module._pipeline.index_chunks([
                {
                    "chunk_id": "is-1",
                    "document_id": "doc-is",
                    "project_id": "proj-is",
                    "content": "internal search test content for GDP analysis",
                    "chunk_type": "paragraph",
                    "page_start": 1,
                    "page_end": 1,
                }
            ])

        asyncio.run(index())

        resp = client.post(
            "/internal/search",
            json={
                "query": "GDP analysis",
                "project_id": "proj-is",
                "top_k": 5,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["total_hits"] > 0

    def test_internal_search_without_project_id(self, client: TestClient) -> None:
        _setup_isolation_test_data()

        import asyncio

        from kb_service import app as app_module

        async def index() -> None:
            await app_module._pipeline.index_chunks([
                {
                    "chunk_id": "ns-1",
                    "document_id": "doc-ns",
                    "project_id": "proj-ns",
                    "content": "no project id search test inflation rate",
                    "chunk_type": "paragraph",
                    "page_start": 1,
                    "page_end": 1,
                }
            ])

        asyncio.run(index())

        resp = client.post(
            "/internal/search",
            json={
                "query": "inflation rate",
                "top_k": 5,
            },
        )
        assert resp.status_code == 200
        # Cross-project, no project_id filter should find results
        assert resp.json()["total_hits"] > 0
