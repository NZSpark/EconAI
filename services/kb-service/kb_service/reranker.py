"""Reranker — cross-encoder rescoring with BGE-Reranker support."""

from __future__ import annotations

import logging
from typing import Any

from kb_service.config import settings

logger = logging.getLogger(__name__)


class Reranker:
    """Re-ranks search results using BGE-Reranker cross-encoder or heuristic fallback."""

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or "BAAI/bge-reranker-v2-m3"
        self._model = None

    async def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from FlagEmbedding import FlagReranker  # type: ignore[import-untyped]

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
        """Rerank candidates by relevance to query."""
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
        query_terms = set(query.lower().split())
        for candidate in candidates:
            content = candidate.get("content", "")
            rrf_score = candidate.get("score", 0.0)
            content_terms = set(content.lower().split())
            overlap = len(query_terms & content_terms) / len(query_terms) if query_terms else 0.0
            candidate["score"] = 0.7 * rrf_score + 0.3 * overlap
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates


class NoopReranker:
    """No-op reranker that returns candidates unchanged."""

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return candidates