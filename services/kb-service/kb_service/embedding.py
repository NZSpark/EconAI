"""Embedding 客户端 —— 通过 LLM Router 生成文本向量，带 Redis 缓存。

核心设计：
- 委托 LLM Router 服务生成 embedding（调用 /internal/llm/embed）
- Redis 缓存：相同文本不重复计算向量（key = kb:emb:{model}:{sha256前32位}）
- 批量接口：embed_batch() 先查缓存，仅对未缓存文本调用 API
- 降级策略：API 失败时返回零向量，不阻塞搜索流程
"""

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
    """为文本块生成 embedding 向量。

    工作流程：
    1. 截断文本到 2048 字符（防止 token 溢出）
    2. 查 Redis 缓存（key = kb:emb:{model}:{sha256前32位}）
    3. 缓存未命中 → 调用 LLM Router 的 /internal/llm/embed 接口
    4. 结果写入 Redis 缓存（TTL 可配置）
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
        """生成缓存键：模型名 + SHA256 前 32 位。"""
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
        return f"kb:emb:{self.model}:{digest}"

    async def _cache_get(self, key: str) -> list[float] | None:
        """从 Redis 读取缓存的向量。"""
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
        """将向量写入 Redis 缓存。"""
        if self._redis is None:
            return
        with contextlib.suppress(Exception):
            await self._redis.setex(key, self.cache_ttl, json.dumps(vec))

    def _truncate_text(self, text: str, max_chars: int = 2048) -> str:
        """截断文本到最大字符数，防止 embedding 模型 token 溢出。"""
        if len(text) <= max_chars:
            return text
        return text[:max_chars]

    async def embed_single(self, text: str) -> list[float]:
        """为单个文本生成 embedding 向量。"""
        truncated = self._truncate_text(text)

        # 查缓存
        key = self._cache_key(truncated)
        cached = await self._cache_get(key)
        if cached is not None:
            return cached

        # 调用 LLM Router 的 embedding API
        vec = await self._call_embedding_api([truncated])
        result = vec[0] if vec else [0.0] * self.dim

        # 写入缓存
        await self._cache_set(key, result)
        return result

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量生成 embedding 向量，带缓存优化。

        流程：
        1. 逐个查 Redis 缓存
        2. 对未缓存的文本，按 batch_size 分批调用 API
        3. 结果回写缓存
        """
        truncated = [self._truncate_text(t) for t in texts]

        results: list[list[float]] = []
        uncached_texts: list[str] = []
        uncached_indices: list[int] = []

        # 第一步：逐个查缓存
        for i, text in enumerate(truncated):
            key = self._cache_key(text)
            cached = await self._cache_get(key)
            if cached is not None:
                results.append(cached)
            else:
                results.append([])  # 占位
                uncached_texts.append(text)
                uncached_indices.append(i)

        if not uncached_texts:
            return results

        # 第二步：分批调用 API
        all_vectors: list[list[float]] = []
        for start in range(0, len(uncached_texts), self.batch_size):
            batch = uncached_texts[start : start + self.batch_size]
            batch_vectors = await self._call_embedding_api(batch)
            all_vectors.extend(batch_vectors)

        # 第三步：填充结果并缓存
        for j, idx in enumerate(uncached_indices):
            vec = all_vectors[j] if j < len(all_vectors) else [0.0] * self.dim
            results[idx] = vec
            await self._cache_set(self._cache_key(uncached_texts[j]), vec)

        return results

    async def _call_embedding_api(self, texts: list[str]) -> list[list[float]]:
        """调用 LLM Router 的 /internal/llm/embed 接口生成向量。"""
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
    """内存 embedding 客户端（测试用）。

    根据文本内容的 SHA256 哈希生成确定性的伪随机向量，
    不依赖外部 API，适合单元测试和 CI 环境。
    """

    def __init__(self, dim: int = 1024) -> None:
        self.model = "mock-embedding"
        self.dim = dim

    def _pseudo_vector(self, text: str) -> list[float]:
        """根据文本 SHA256 哈希生成确定性向量。"""
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
