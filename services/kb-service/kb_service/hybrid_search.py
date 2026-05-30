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
    """混合搜索引擎 —— 融合向量语义搜索 + BM25 关键词搜索。

    搜索管线：
      1. 并行执行：向量搜索（top_k=50）+ BM25 关键词搜索（top_k=50）
      2. RRF（倒数排名融合）合并两个结果列表 → top_k=30
      3. （可选）BGE-Reranker 交叉编码器重排序
      4. 返回最终 top_k 结果 + 分页

    为什么用混合搜索？
    - 向量搜索擅长语义匹配（"经济增长"能匹配到"GDP上升"）
    - BM25 擅长精确关键词匹配（搜"碳排放"不会漏掉标题包含"碳排放"的文档）
    - RRF 融合两者优势，不依赖分数归一化
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
        # 重排序器：生产环境用 BGE-Reranker，测试用 NoopReranker（透传）
        self.reranker = reranker or (Reranker() if settings.reranker_enabled else NoopReranker())
        self.rrf_k = settings.hybrid_rrf_k               # RRF 融合参数 k（默认60）
        self.vector_top_k = settings.hybrid_vector_top_k # 向量搜索召回数（默认50）
        self.bm25_top_k = settings.hybrid_bm25_top_k     # BM25 搜索召回数（默认50）
        self.merged_top_k = settings.hybrid_merged_top_k # RRF 融合后保留数（默认30）
        self.default_top_k = settings.search_default_top_k
        self.timeout_ms = settings.search_timeout_ms     # 搜索超时（毫秒）

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        project_id: str | None = None,
        document_ids: list[str] | None = None,
        chunk_types: list[str] | None = None,
        search_mode: str = "hybrid",
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[dict[str, Any]], int, float]:
        """执行混合搜索，支持分页。

        search_mode 可选值：
        - "hybrid": 向量 + BM25 + RRF 融合（默认，推荐）
        - "vector": 仅向量语义搜索
        - "bm25":   仅 BM25 关键词搜索

        Returns:
            Tuple of (results, total_hits, search_time_ms).
        """
        start = time.monotonic()
        final_top_k = top_k or self.default_top_k

        # 第一步：将查询文本转为向量（embedding）
        query_vector = await self.embedding_client.embed_single(query)

        # 第二步：构建向量搜索的过滤条件
        vector_filters: dict[str, Any] = {}
        if project_id:
            vector_filters["project_id"] = project_id
        if document_ids:
            vector_filters["document_ids"] = document_ids

        # 纯向量搜索模式
        if search_mode == "vector":
            vec_results = await self._vector_search_with_timeout(query_vector, self.vector_top_k, vector_filters)
            total = len(vec_results)
            sliced = self._paginate(vec_results[:final_top_k], page, page_size)
            elapsed_ms = (time.monotonic() - start) * 1000
            return sliced, total, elapsed_ms

        # 纯 BM25 关键词搜索模式
        if search_mode == "bm25":
            bm25_results = await self._bm25_search_with_timeout(
                query, self.bm25_top_k, project_id, document_ids, chunk_types
            )
            total = len(bm25_results)
            sliced = self._paginate(bm25_results[:final_top_k], page, page_size)
            elapsed_ms = (time.monotonic() - start) * 1000
            return sliced, total, elapsed_ms

        # 混合模式：并行执行向量搜索 + BM25 搜索
        # asyncio.gather 同时发起两个搜索，哪个先完成都不会阻塞另一个
        vec_results, bm25_results = await asyncio.gather(
            self._vector_search_with_timeout(query_vector, self.vector_top_k, vector_filters),
            self._bm25_search_with_timeout(query, self.bm25_top_k, project_id, document_ids, chunk_types),
        )

        # 第三步：RRF 倒数排名融合
        # 两个搜索结果各自按排名计分，分数相加得到最终排名
        fused = self._rrf_fusion(vec_results, bm25_results, self.rrf_k)[: self.merged_top_k]

        # 第四步：可选的交叉编码器重排序（BGE-Reranker）
        if settings.reranker_enabled:
            fused = await self.reranker.rerank(query, fused)

        total = len(fused)
        sliced = self._paginate(fused[:final_top_k], page, page_size)
        elapsed_ms = (time.monotonic() - start) * 1000
        return sliced, total, elapsed_ms

    @staticmethod
    def _paginate(
        results: list[dict[str, Any]], page: int, page_size: int
    ) -> list[dict[str, Any]]:
        """Slice results according to page/page_size."""
        if page < 1:
            page = 1
        start_idx = (page - 1) * page_size
        return results[start_idx : start_idx + page_size]

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
        """RRF 倒数排名融合：score = SUM(1 / (k + rank))。
        
        为什么用 RRF 而不是简单加权？
        - 向量搜索的分数是余弦相似度（0-1），BM25 分数是 TF-IDF（无上界）
        - 两种分数的量纲不同，无法直接相加或加权
        - RRF 只看排名不看原始分数：rank=1 得 1/(k+1)，rank=50 得 1/(k+50)
        - 一个 chunk 同时在向量搜索排第3、BM25排第5 → 最终分 = 1/63 + 1/65
        
        k=60 是经验值：太小会让排名靠后的结果差距过大，太大会让所有结果分数趋同
        """
        scores: dict[str, float] = {}         # chunk_id → RRF 融合分数
        merged: dict[str, dict[str, Any]] = {} # chunk_id → 合并后的 chunk 数据

        # 向量搜索结果：rank 越小（排名越靠前），RRF 分数越高
        for rank, result in enumerate(vec_results, start=1):
            cid = result["chunk_id"]
            rrf_score = 1.0 / (k + rank)
            scores[cid] = scores.get(cid, 0.0) + rrf_score
            if cid not in merged:
                merged[cid] = dict(result)

        # BM25 搜索结果：同样计算 RRF 分数并累加
        for rank, result in enumerate(bm25_results, start=1):
            cid = result["chunk_id"]
            rrf_score = 1.0 / (k + rank)
            scores[cid] = scores.get(cid, 0.0) + rrf_score
            if cid not in merged:
                merged[cid] = dict(result)

        # 按 RRF 融合分数降序排列
        sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
        for cid in sorted_ids:
            merged[cid]["score"] = scores[cid]

        return [merged[cid] for cid in sorted_ids]
