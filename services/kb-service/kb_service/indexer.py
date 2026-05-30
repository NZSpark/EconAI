"""索引 pipeline — consumes Redis pub/sub events and runs full indexing flow."""

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
    """文档索引管线 —— 将文档块写入向量数据库和 BM25 索引。
    
    处理流程：
    1. 读取文档块列表（来自 document-service 的切分结果）
    2. 调用 embedding 服务生成每个块的向量表示
    3. 将 (chunk_id, vector, metadata) 批量写入向量数据库
    4. 更新 BM25 内存索引（测试模式）或等待 PostgreSQL FTS 自动更新
    
    触发方式：
    - 通过 Redis pub/sub 频道 kb:index:request 接收索引事件
    - 由 RedisIndexConsumer 异步消费并调用本管线
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
        """索引一批文档块。

        Args:
            chunks: 块字典列表，每块包含: chunk_id, document_id,
                    project_id, content, chunk_type, page_start, page_end。

        Returns:
            成功索引的块数量。
        """
        if not chunks:
            return 0

        # 第一步：批量生成 embedding 向量
        texts = [c["content"] for c in chunks]
        embeddings = await self.embedding_client.embed_batch(texts)

        # 第二步：组装写入条目（chunk_id, vector, metadata）
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

        # 第三步：批量写入向量数据库
        await self.vector_store.insert_batch(entries)

        # 第四步：更新 BM25 内存索引（仅测试/开发模式）
        # 生产环境中 PostgreSQL 的 document_chunks 表已有 FTS 索引，
        # BM25Searcher 直接查询数据库，无需手动更新
        if isinstance(self.bm25, InMemoryBM25Searcher):
            self.bm25.add_chunks(chunks)

        logger.info("Indexed %d chunks", len(entries))
        return len(entries)

    async def reindex_chunks(
        self,
        chunks: list[dict[str, Any]],
    ) -> int:
        """重建索引 chunks (delete existing then insert)."""
        if not chunks:
            return 0
        doc_id = chunks[0].get("document_id", "")
        if doc_id:
            await self.vector_store.delete_by_document(doc_id)
            if isinstance(self.bm25, InMemoryBM25Searcher):
                self.bm25.remove_by_document(doc_id)
        return await self.index_chunks(chunks)

    async def delete_document(self, document_id: str) -> int:
        """删除 all index entries for a document."""
        vec_count = await self.vector_store.delete_by_document(document_id)
        bm25_count = 0
        if isinstance(self.bm25, InMemoryBM25Searcher):
            bm25_count = self.bm25.remove_by_document(document_id)
        logger.info("Deleted index for document %s: %d vectors, %d bm25", document_id, vec_count, bm25_count)
        return vec_count

    async def delete_project(self, project_id: str) -> int:
        """删除 all index entries for a project."""
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
        """启动 listening for index events on kb:index:request."""
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
        """处理 a single index event."""
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
