"""重排序器 —— 使用 BGE-Reranker 交叉编码器或启发式方法对搜索结果重排序。

为什么需要重排序？
- 向量搜索和 BM25 都使用双编码器（bi-encoder），query 和 doc 独立编码
- 双编码器速度快但精度有限，无法捕捉 query 和 doc 之间的细粒度交互
- 交叉编码器（cross-encoder）将 query+doc 拼接后一起编码，精度更高但速度慢
- 策略：先召回 50 条（快速），再重排序取 top-K（精确）
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class Reranker:
    """使用 BGE-Reranker 交叉编码器对搜索结果重排序。
    
    降级策略：
    - BGE-Reranker 可用 → 交叉编码器精确重排序
    - FlagEmbedding 未安装 → 启发式重排序（query-doc 词重叠加权）
    """

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or "BAAI/bge-reranker-v2-m3"
        self._model = None

    async def _load_model(self) -> Any:
        """延迟加载 BGE-Reranker 模型（首次使用时加载）。"""
        if self._model is not None:
            return self._model
        try:
            from FlagEmbedding import FlagReranker

            self._model = FlagReranker(self._model_name, use_fp16=True)
            logger.info("Loaded BGE-Reranker model: %s", self._model_name)
            return self._model
        except ImportError:
            logger.warning("FlagEmbedding not installed, using heuristic reranker fallback")
            return None
        except Exception:
            logger.exception("Failed to load BGE-Reranker, using heuristic fallback")
            return None

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """对候选结果按与查询的相关性重排序。"""
        model = await self._load_model()
        if model is not None:
            return await self._cross_encoder_rerank(model, query, candidates)
        return self._heuristic_rerank(query, candidates)

    async def _cross_encoder_rerank(
        self,
        model: Any,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """BGE-Reranker 交叉编码器：将每对 (query, chunk_content) 输入模型打分。"""
        pairs = [[query, c.get("content", "")] for c in candidates]
        scores = model.compute_score(pairs)
        if not isinstance(scores, list):
            scores = [scores]
        for i, score in enumerate(scores):
            candidates[i]["rerank_score"] = float(score)
        candidates.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
        return candidates

    @staticmethod
    def _heuristic_rerank(
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """启发式重排序：RRF 分数（70%权重）+ query-doc 词重叠率（30%权重）。
        
        这是一个简单的后备方案，不需要额外模型。
        """
        query_terms = set(query.lower().split())
        for candidate in candidates:
            content = candidate.get("content", "")
            rrf_score = candidate.get("score", 0.0)
            content_terms = set(content.lower().split())
            # 词重叠率：query 中有多少比例的 token 在 doc 中出现
            overlap = len(query_terms & content_terms) / len(query_terms) if query_terms else 0.0
            candidate["score"] = 0.7 * rrf_score + 0.3 * overlap
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates


class NoopReranker:
    """透传重排序器 —— 不做任何处理，直接返回原始结果。"""

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return candidates
