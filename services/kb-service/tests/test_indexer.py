"""Tests for index pipeline and Redis pub/sub consumption (M3-35)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from kb_service.bm25 import InMemoryBM25Searcher
from kb_service.embedding import MockEmbeddingClient
from kb_service.indexer import IndexPipeline
from kb_service.lifecycle import LifecycleManager
from kb_service.schemas import IndexEvent
from kb_service.vector_store import InMemoryVectorStore


class FakeRedisWithPubSub:
    """Redis mock with pub/sub support for testing."""

    def __init__(self) -> None:
        self._channels: dict[str, list[dict[str, Any]]] = {}
        self._subscribers: dict[str, list[Any]] = {}

    def pubsub(self) -> FakePubSub:
        return FakePubSub(self)

    async def publish(self, channel: str, message: str) -> int:
        if channel not in self._channels:
            self._channels[channel] = []
        self._channels[channel].append(json.loads(message))
        return 1


class FakePubSub:
    def __init__(self, redis: FakeRedisWithPubSub) -> None:
        self._redis = redis
        self._subscribed: list[str] = []
        self._messages: list[dict[str, Any]] = []
        self._index = 0

    async def subscribe(self, channel: str) -> None:
        self._subscribed.append(channel)

    async def unsubscribe(self, channel: str) -> None:
        if channel in self._subscribed:
            self._subscribed.remove(channel)

    async def get_message(self, ignore_subscribe_messages: bool = True, timeout: float = 1.0) -> dict[str, Any] | None:
        if self._index < len(self._messages):
            msg = self._messages[self._index]
            self._index += 1
            return msg
        return None

    def add_message(self, data: dict[str, Any]) -> None:
        self._messages.append({"type": "message", "data": json.dumps(data)})


def _make_chunks(project_id: str = "proj-1", count: int = 5) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": f"chunk-{i}",
            "document_id": "doc-1",
            "project_id": project_id,
            "content": f"Chunk {i} about fiscal policy and economic development",
            "chunk_type": "paragraph",
            "page_start": i,
            "page_end": i,
        }
        for i in range(count)
    ]


@pytest.fixture
def pipeline() -> IndexPipeline:
    vs = InMemoryVectorStore(dim=768)
    emb = MockEmbeddingClient(dim=768)
    bm25 = InMemoryBM25Searcher()
    return IndexPipeline(vector_store=vs, embedding_client=emb, bm25_searcher=bm25)


class TestIndexPipeline:
    @pytest.mark.asyncio
    async def test_index_chunks_inserts_into_vector_store(self, pipeline: IndexPipeline) -> None:
        chunks = _make_chunks()
        count = await pipeline.index_chunks(chunks)
        assert count == 5

        emb = MockEmbeddingClient(dim=768)
        query_vec = emb._pseudo_vector("fiscal policy")
        results = await pipeline.vector_store.search(query_vec, top_k=10)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_index_chunks_bm25(self, pipeline: IndexPipeline) -> None:
        chunks = _make_chunks()
        await pipeline.index_chunks(chunks)

        assert pipeline.bm25 is not None
        bm25_results = await pipeline.bm25.search(query="fiscal policy", top_k=5)
        assert len(bm25_results) > 0

    @pytest.mark.asyncio
    async def test_index_empty_chunks(self, pipeline: IndexPipeline) -> None:
        count = await pipeline.index_chunks([])
        assert count == 0

    @pytest.mark.asyncio
    async def test_delete_document_removes_from_both_stores(self, pipeline: IndexPipeline) -> None:
        chunks = _make_chunks()
        await pipeline.index_chunks(chunks)

        count = await pipeline.delete_document("doc-1")
        assert count == 5

        emb = MockEmbeddingClient(dim=768)
        query_vec = emb._pseudo_vector("fiscal")
        results = await pipeline.vector_store.search(query_vec, top_k=10)
        assert len(results) == 0

        assert pipeline.bm25 is not None
        bm25_results = await pipeline.bm25.search(query="fiscal policy", top_k=5)
        assert len(bm25_results) == 0

    @pytest.mark.asyncio
    async def test_delete_project_removes_all_chunks(self, pipeline: IndexPipeline) -> None:
        chunks_a = _make_chunks("proj-a", count=3)
        chunks_b = _make_chunks("proj-b", count=2)
        await pipeline.index_chunks(chunks_a)
        await pipeline.index_chunks(chunks_b)

        count = await pipeline.delete_project("proj-a")
        assert count == 3

        emb = MockEmbeddingClient(dim=768)
        query_vec = emb._pseudo_vector("economic")
        results = await pipeline.vector_store.search(query_vec, top_k=10)
        assert all(r["metadata"]["project_id"] == "proj-b" for r in results)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_reindex_chunks(self, pipeline: IndexPipeline) -> None:
        chunks = _make_chunks()
        await pipeline.index_chunks(chunks)

        new_chunks: list[dict[str, Any]] = [
            {
                "chunk_id": "chunk-new-0",
                "document_id": "doc-1",
                "project_id": "proj-1",
                "content": "New reindexed content about monetary policy",
                "chunk_type": "paragraph",
                "page_start": 0,
                "page_end": 0,
            }
        ]
        count = await pipeline.reindex_chunks(new_chunks)
        assert count == 1

        results = await pipeline.vector_store.search(
            MockEmbeddingClient(dim=768)._pseudo_vector("monetary"),
            top_k=10,
        )
        assert len(results) == 1
        assert results[0]["chunk_id"] == "chunk-new-0"


class TestLifecycleManager:
    @pytest.mark.asyncio
    async def test_delete_document_cascade(self, pipeline: IndexPipeline) -> None:
        lm = LifecycleManager(pipeline)
        chunks = _make_chunks()
        await pipeline.index_chunks(chunks)

        result = await lm.delete_document("doc-1")
        assert result["status"] == "deleted"
        assert result["deleted_vectors"] == 5

    @pytest.mark.asyncio
    async def test_delete_project_cascade(self, pipeline: IndexPipeline) -> None:
        lm = LifecycleManager(pipeline)
        chunks = _make_chunks("proj-del", count=4)
        await pipeline.index_chunks(chunks)

        result = await lm.delete_project("proj-del")
        assert result["status"] == "deleted"
        assert result["deleted_vectors"] == 4

    @pytest.mark.asyncio
    async def test_reindex_project(self, pipeline: IndexPipeline) -> None:
        lm = LifecycleManager(pipeline)
        chunks = _make_chunks("proj-reidx", count=3)
        await pipeline.index_chunks(chunks)

        new_chunks: list[dict[str, Any]] = [
            {
                "chunk_id": f"new-chunk-{i}",
                "document_id": "doc-new",
                "project_id": "proj-reidx",
                "content": f"Reindexed chunk {i} about trade policy",
                "chunk_type": "paragraph",
                "page_start": i,
                "page_end": i,
            }
            for i in range(2)
        ]
        result = await lm.reindex_project("proj-reidx", new_chunks)
        assert result["status"] == "reindexed"
        assert result["indexed_chunks"] == 2


class TestIndexEvent:
    def test_index_event_parsing(self) -> None:
        event = IndexEvent(
            event_id="evt-001",
            document_id="doc-abc",
            project_id="proj-xyz",
            chunk_ids=["c1", "c2", "c3"],
            is_internal=False,
            timestamp="2026-05-17T10:00:00",
            event_type="document.parsed",
        )
        assert event.event_id == "evt-001"
        assert event.document_id == "doc-abc"
        assert event.project_id == "proj-xyz"
        assert len(event.chunk_ids) == 3

    def test_index_event_defaults(self) -> None:
        event = IndexEvent(
            event_id="evt-002",
            document_id="doc-def",
            project_id="proj-ghi",
        )
        assert event.event_type == "document.parsed"
        assert event.chunk_ids == []
        assert event.is_internal is False


class TestVectorStore:
    @pytest.mark.asyncio
    async def test_initial_state_empty(self) -> None:
        vs = InMemoryVectorStore(dim=128)
        results = await vs.search([0.0] * 128, top_k=5)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_insert_and_search(self) -> None:
        vs = InMemoryVectorStore(dim=4)
        await vs.insert("a", [1.0, 0.0, 0.0, 0.0], {"project_id": "p1"})
        await vs.insert("b", [0.0, 1.0, 0.0, 0.0], {"project_id": "p1"})
        await vs.insert("c", [0.9, 0.1, 0.0, 0.0], {"project_id": "p1"})

        results = await vs.search([1.0, 0.0, 0.0, 0.0], top_k=2)
        assert results[0]["chunk_id"] == "a"
        assert results[0]["score"] > 0.9

    @pytest.mark.asyncio
    async def test_filter_by_project(self) -> None:
        vs = InMemoryVectorStore(dim=4)
        await vs.insert("a", [1.0, 0.0, 0.0, 0.0], {"project_id": "p1"})
        await vs.insert("b", [1.0, 0.0, 0.0, 0.0], {"project_id": "p2"})

        results = await vs.search([1.0, 0.0, 0.0, 0.0], top_k=5, filters={"project_id": "p1"})
        assert len(results) == 1
        assert results[0]["chunk_id"] == "a"

    @pytest.mark.asyncio
    async def test_delete_by_document(self) -> None:
        vs = InMemoryVectorStore(dim=4)
        await vs.insert("a", [1.0, 0.0, 0.0, 0.0], {"document_id": "doc-1"})
        await vs.insert("b", [0.0, 1.0, 0.0, 0.0], {"document_id": "doc-2"})

        count = await vs.delete_by_document("doc-1")
        assert count == 1

        results = await vs.search([1.0, 0.0, 0.0, 0.0], top_k=5)
        assert len(results) == 1
        assert results[0]["chunk_id"] == "b"

    @pytest.mark.asyncio
    async def test_insert_batch(self) -> None:
        vs = InMemoryVectorStore(dim=4)
        entries: list[tuple[str, list[float], dict[str, Any]]] = [
            ("c1", [1.0, 0.0, 0.0, 0.0], {"doc": "d1"}),
            ("c2", [0.0, 1.0, 0.0, 0.0], {"doc": "d1"}),
            ("c3", [0.0, 0.0, 1.0, 0.0], {"doc": "d2"}),
        ]
        await vs.insert_batch(entries)
        results = await vs.search([1.0, 0.0, 0.0, 0.0], top_k=5)
        assert len(results) == 3
