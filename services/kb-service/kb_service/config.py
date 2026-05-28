"""KB Service configuration via pydantic-settings."""

from functools import lru_cache

from pydantic_settings import SettingsConfigDict
from shared.config import AppSettings


class KBSettings(AppSettings):
    """Knowledge Base Service configuration — inherits common DB/Redis/JWT from AppSettings."""

    # Service identity
    service_name: str = "kb-service"
    service_port: int = 8002

    # Override parent computed properties with direct defaults for Docker compatibility
    database_url: str = "postgresql+asyncpg://econai:econai_secret_change_me@localhost:5432/econai"
    redis_url: str = "redis://localhost:6379/0"

    # Vector DB
    vector_db_type: str = "milvus"
    vector_db_host: str = "localhost"
    vector_db_port: int = 19530
    vector_db_collection: str = "econai_chunks"

    # Embedding
    embedding_model: str = "text2vec-large-chinese"
    embedding_dim: int = 1024
    embedding_batch_size: int = 32
    embedding_cache_ttl: int = 86400

    # LLM Router (for generating embeddings)
    llm_router_url: str = "http://localhost:8004"

    # Hybrid search
    hybrid_vector_top_k: int = 50
    hybrid_bm25_top_k: int = 50
    hybrid_rrf_k: int = 60
    hybrid_merged_top_k: int = 30
    search_default_top_k: int = 10
    search_timeout_ms: int = 5000
    reranker_enabled: bool = False

    model_config = SettingsConfigDict(
        env_prefix="KB_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )


@lru_cache
def get_settings() -> KBSettings:
    return KBSettings()


settings = get_settings()
