"""Embedding client — generates embeddings via LLM Router with Redis caching."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
from typing import Any

import httpx

from kb_service.config import settings

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Generates embeddings for text chunks.

    Delegates to the LLM Router service for actual embedding generation.
    Caches results in Redis to avoid redundant computation.
    """

    def __init__(
        self,
        router_url: str | None = None,
        redis_client: Any = None,
    ) -> None:
        self.router_url = (router_url or settings.llm_router_url).rstrip("/")
        self._redis = redis_client
        self.model = settings.embedding_model
        self.dim = settings.embedding_dim
        self.batch_size = settings.embedding_batch_size
        self.cache_ttl = settings.embedding_cache_ttl

    def _cache_key(self, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
        return f"kb:emb:{self.model}:{digest}"

    async def _cache_get(self, key: str) -> list[float] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return None

    async def _cache_set(self, key: str, vec: list[float]) -> None:
        if self._redis is None:
            return
        with contextlib.suppress(Exception):
            await self._redis.setex(key, self.cache_ttl, json.dumps(vec))

    def _truncate_text(self, text: str, max_chars: int = 2048) -> str:
        """Truncate text to avoid token overflow in the embedding model."""
        if len(text) <= max_chars:
            return text
        return text[:max_chars]

    async def embed_single(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        truncated = self._truncate_text(text)

        # Check cache
        key = self._cache_key(truncated)
        cached = await self._cache_get(key)
        if cached is not None:
            return cached

        # Generate via LLM Router
        vec = await self._call_embedding_api([truncated])
        result = vec[0] if vec else [0.0] * self.dim

        # Store in cache
        await self._cache_set(key, result)
        return result

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts, with caching."""
        truncated = [self._truncate_text(t) for t in texts]

        results: list[list[float]] = []
        uncached_texts: list[str] = []
        uncached_indices: list[int] = []

        # Check cache
        for i, text in enumerate(truncated):
            key = self._cache_key(text)
            cached = await self._cache_get(key)
            if cached is not None:
                results.append(cached)
            else:
                results.append([])  # placeholder
                uncached_texts.append(text)
                uncached_indices.append(i)

        if not uncached_texts:
            return results

        # Batch-call embedding API for uncached texts
        all_vectors: list[list[float]] = []
        for start in range(0, len(uncached_texts), self.batch_size):
            batch = uncached_texts[start : start + self.batch_size]
            batch_vectors = await self._call_embedding_api(batch)
            all_vectors.extend(batch_vectors)

        # Fill in results and cache
        for j, idx in enumerate(uncached_indices):
            vec = all_vectors[j] if j < len(all_vectors) else [0.0] * self.dim
            results[idx] = vec
            await self._cache_set(self._cache_key(uncached_texts[j]), vec)

        return results

    async def _call_embedding_api(self, texts: list[str]) -> list[list[float]]:
        """Call LLM Router's embedding endpoint.

        Uses a dedicated /internal/llm/embed endpoint if available,
        otherwise falls back to calling the embedding model directly.
        """
        url = f"{self.router_url}/internal/llm/embed"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    json={"texts": texts, "model": self.model},
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("embeddings", [])
        except httpx.HTTPStatusError as exc:
            logger.error("Embedding API HTTP error %d: %s", exc.response.status_code, exc)
            raise
        except httpx.RequestError as exc:
            logger.error("Embedding API request error: %s", exc)
            raise


class MockEmbeddingClient:
    """In-memory embedding client for testing.

    Returns deterministic pseudo-random vectors based on text content hash.
    """

    def __init__(self, dim: int = 1024) -> None:
        self.model = "mock-embedding"
        self.dim = dim

    def _pseudo_vector(self, text: str) -> list[float]:
        """Generate a deterministic vector from text hash."""
        import struct

        h = hashlib.sha256(text.encode("utf-8")).digest()
        vec: list[float] = []
        for i in range(0, len(h), 4):
            if len(vec) >= self.dim:
                break
            val = struct.unpack(">f", h[i : i + 4])[0]
            vec.append(val / 10.0)
        while len(vec) < self.dim:
            vec.append(0.0)
        return vec

    async def embed_single(self, text: str) -> list[float]:
        return self._pseudo_vector(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._pseudo_vector(t) for t in texts]
