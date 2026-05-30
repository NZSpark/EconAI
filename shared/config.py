"""Base configuration via pydantic-settings, shared across all services."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Base settings all microservices inherit from.

    Each service can subclass and add its own env-prefixed settings.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    # General
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "policyai"
    postgres_user: str = "policyai"
    postgres_password: str = "policyai_secret_change_me"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = "policyai_redis_change_me"

    # JWT
    jwt_secret: str = "policyai_jwt_secret_change_me_min_32_chars"
    jwt_algorithm: str = "HS256"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}"


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
