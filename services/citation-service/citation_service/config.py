"""Configuration management for the Citation Service (M6-02).

Configures: similarity threshold (0.85), batch verify size, footnote/endnote default settings.
"""

from pydantic_settings import BaseSettings


class CitationConfig(BaseSettings):
    """Configuration for the Citation Service."""

    # Service identity
    SERVICE_NAME: str = "citation-service"
    SERVICE_PORT: int = 8005

    # Citation verification
    CITATION_SIMILARITY_THRESHOLD: float = 0.85
    CITATION_VERIFY_BATCH_SIZE: int = 50

    # Citation formatting
    CITATION_FORMAT_FOOTNOTE: bool = True  # True = footnote, False = endnote for .docx

    # Database (optional, for persistence subtasks)
    DATABASE_URL: str = "postgresql+asyncpg://localhost:5432/econai"

    # Redis (optional, for service communication)
    REDIS_URL: str = "redis://localhost:6379/0"

    model_config = {"env_prefix": "CITATION_", "case_sensitive": True}


# Singleton instance
config = CitationConfig()
