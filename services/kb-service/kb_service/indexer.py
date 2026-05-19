"""Index pipeline — consumes Redis pub/sub events and runs full indexing flow."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from kb_service.bm25 import BM25Searcher, InMemoryBM25Searcher
from kb_service.embedding import EmbeddingClient, MockEmbeddingClient
from kb_service.schemas import IndexEvent
from kb_service.vector_store import InMemoryVectorStore, VectorStore

logger = logging.getLogger(__name__)


class IndexPipeline:
    """Runs the full indexing flow for document chunks.

    Flow: read chunks → generate embeddings → write vector DB → update BM25.
    """

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        embedding_client: EmbeddingClient | MockEmbeddingClient | None = None,
        bm25_searcher: BM25Searcher | InMemoryBM25Searcher | None = None,
    ) -> None:
        self.vector_store = vector_store or InMemoryVectorStore()
        self.embedding_client = embedding_client or MockEmbeddingClient()
        self.bm25 = bm25_searcher

    async def index_chunks(
        self,
        chunks: list[dict[str, Any]],
    ) -> int:
        """Index a batch of chunks.

        Args:
            chunks: List of chunk dicts with keys: chunk_id, document_id,
                    project_id, content, chunk_type, page_start, page_end.

        Returns:
            Number of chunks indexed.
        """
        if not chunks:
            return 0

        texts = [c["content"] for c in chunks]
        embeddings = await self.embedding_client.embed_batch(texts)

        entries: list[tuple[str, list[float], dict[str, Any]]] = []
        for chunk, vec in zip(chunks, embeddings, strict=False):
            metadata = {
                "document_id": chunk.get("document_id", ""),
                "project_id": chunk.get("project_id", ""),
                "chunk_type": chunk.get("chunk_type", ""),
                "content": chunk.get("content", ""),
                "page_start": chunk.get("page_start", 0),
                "page_end": chunk.get("page_end", 0),
            }
            entries.append((chunk["chunk_id"], vec, metadata))

        await self.vector_store.insert_batch(entries)

        if isinstance(self.bm25, InMemoryBM25Searcher):
            self.bm25.add_chunks(chunks)

        logger.info("Indexed %d chunks", len(entries))
        return len(entries)

    async def reindex_chunks(
        self,
        chunks: list[dict[str, Any]],
    ) -> int:
        """Reindex chunks (delete existing then insert)."""
        if not chunks:
            return 0
        doc_id = chunks[0].get("document_id", "")
        if doc_id:
            await self.vector_store.delete_by_document(doc_id)
            if isinstance(self.bm25, InMemoryBM25Searcher):
                self.bm25.remove_by_document(doc_id)
        return await self.index_chunks(chunks)

    async def delete_document(self, document_id: str) -> int:
        """Delete all index entries for a document."""
        vec_count = await self.vector_store.delete_by_document(document_id)
        bm25_count = 0
        if isinstance(self.bm25, InMemoryBM25Searcher):
            bm25_count = self.bm25.remove_by_document(document_id)
        logger.info("Deleted index for document %s: %d vectors, %d bm25", document_id, vec_count, bm25_count)
        return vec_count

    async def delete_project(self, project_id: str) -> int:
        """Delete all index entries for a project."""
        vec_count = await self.vector_store.delete_by_project(project_id)
        bm25_count = 0
        if isinstance(self.bm25, InMemoryBM25Searcher):
            bm25_count = self.bm25.remove_by_project(project_id)
        logger.info("Deleted index for project %s: %d vectors, %d bm25", project_id, vec_count, bm25_count)
        return vec_count


class RedisIndexConsumer:
    """Listens on Redis pub/sub channel kb:index:request for index events.

    When an event is received, fetches chunks from PostgreSQL and runs the index pipeline.
    """

    def __init__(
        self,
        redis_client: Any,
        pipeline: IndexPipeline,
    ) -> None:
        self._redis = redis_client
        self._pipeline = pipeline
        self._running = False

    async def start(self) -> None:
        """Start listening for index events on kb:index:request."""
        self._running = True
        pubsub = self._redis.pubsub()
        await pubsub.subscribe("kb:index:request")

        logger.info("Redis consumer started, listening on kb:index:request")

        while self._running:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("type") == "message":
                    await self._handle_message(json.loads(message["data"]))
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error handling index event")

        await pubsub.unsubscribe("kb:index:request")
        logger.info("Redis consumer stopped")

    def stop(self) -> None:
        """Signal the consumer loop to stop."""
        self._running = False

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """Handle a single index event."""
        try:
            event = IndexEvent(**data)
            logger.info("Received index event: %s for document %s", event.event_id, event.document_id)

            # In a full implementation, fetch chunks from PostgreSQL here.
            # For the in-memory mode, chunks are added directly via index_chunks().
            logger.info(
                "Index event processed: doc=%s project=%s chunks=%d",
                event.document_id,
                event.project_id,
                len(event.chunk_ids),
            )
        except Exception:
            logger.exception("Failed to parse index event")
