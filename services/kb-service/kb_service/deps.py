"""Dependency injection — creates KB service components based on environment config.

Reads settings (VECTOR_DB_TYPE, KB_RERANKER_ENABLED, etc.) and returns the
appropriate real or in-memory implementations. Tests inject their own mocks
directly so this module is only loaded in dev/prod.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from kb_service.config import settings

if TYPE_CHECKING:
    from kb_service.bm25 import BM25Searcher, InMemoryBM25Searcher
    from kb_service.embedding import EmbeddingClient, MockEmbeddingClient
    from kb_service.vector_store import InMemoryVectorStore, VectorStore

logger = logging.getLogger(__name__)


def create_vector_store() -> VectorStore | InMemoryVectorStore:
    """Create the configured VectorStore.

    Returns a Milvus client when vector_db_type='milvus', Qdrant when 'qdrant',
    or InMemoryVectorStore for development/testing.
    """
    db_type = settings.vector_db_type.lower()

    if db_type == "milvus":
        try:
            from kb_service.milvus_store import MilvusVectorStore

            logger.info("Using MilvusVectorStore at %s:%d", settings.vector_db_host, settings.vector_db_port)
            return MilvusVectorStore(
                host=settings.vector_db_host,
                port=settings.vector_db_port,
                collection_name=settings.vector_db_collection,
                dim=settings.embedding_dim,
            )
        except ImportError as exc:
            logger.warning("pymilvus not installed, falling back to InMemoryVectorStore: %s", exc)
        except Exception as exc:
            logger.error("Failed to create MilvusVectorStore, falling back to InMemoryVectorStore: %s", exc)

    if db_type == "qdrant":
        try:
            from kb_service.qdrant_store import QdrantVectorStore

            logger.info("Using QdrantVectorStore at %s:%d", settings.vector_db_host, settings.vector_db_port)
            return QdrantVectorStore(
                host=settings.vector_db_host,
                port=settings.vector_db_port,
                collection_name=settings.vector_db_collection,
                dim=settings.embedding_dim,
            )
        except ImportError as exc:
            logger.warning("qdrant-client not installed, falling back to InMemoryVectorStore: %s", exc)
        except Exception as exc:
            logger.error("Failed to create QdrantVectorStore, falling back to InMemoryVectorStore: %s", exc)

    logger.info("Using InMemoryVectorStore (vector_db_type=%s)", db_type)
    from kb_service.vector_store import InMemoryVectorStore

    return InMemoryVectorStore(dim=settings.embedding_dim)


def create_embedding_client() -> EmbeddingClient | MockEmbeddingClient:
    """Create the configured embedding client.

    Uses the real EmbeddingClient (delegates to LLM Router) in production,
    MockEmbeddingClient for development/testing when LLM Router is unavailable.
    """
    if settings.embedding_model == "mock":
        from kb_service.embedding import MockEmbeddingClient

        logger.info("Using MockEmbeddingClient")
        return MockEmbeddingClient(dim=settings.embedding_dim)

    from kb_service.embedding import EmbeddingClient

    logger.info("Using EmbeddingClient (model=%s, router=%s)", settings.embedding_model, settings.llm_router_url)
    return EmbeddingClient(
        router_url=settings.llm_router_url,
    )


def create_bm25_searcher() -> BM25Searcher | InMemoryBM25Searcher:
    """Create the configured BM25 searcher.

    Uses PostgreSQL FTS BM25Searcher when a database_url is configured,
    InMemoryBM25Searcher for development/testing.
    """
    if settings.database_url and "localhost" not in settings.database_url:
        from kb_service.bm25 import BM25Searcher

        logger.info("Using BM25Searcher (PostgreSQL FTS)")
        return BM25Searcher()

    logger.info("Using InMemoryBM25Searcher (no remote DB configured)")
    from kb_service.bm25 import InMemoryBM25Searcher

    return InMemoryBM25Searcher()
