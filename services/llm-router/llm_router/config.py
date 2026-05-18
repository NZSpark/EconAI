"""LLM Router configuration via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """LLM Router service configuration.

    All values can be overridden via environment variables (uppercase).
    """

    model_config = SettingsConfigDict(env_prefix="LLM_", case_sensitive=False)

    # Anthropic / Claude API
    anthropic_api_key: str = ""
    cloud_llm_default_model: str = "claude-sonnet-4-6"

    # Local LLM (OpenAI-compatible API)
    local_llm_endpoint: str = "http://localhost:8000/v1"
    local_llm_api_key: str = "not-needed"
    local_llm_default_model: str = "local:qwen3-72b"

    # Model registry config file path
    model_registry_path: str = "models.yaml"

    # Default generation parameters
    llm_default_temperature: float = 0.3
    llm_default_max_tokens: int = 4096
    llm_max_context_tokens: int = 200000

    # Request timeout
    llm_request_timeout_s: int = 120

    # Retry configuration
    llm_retry_max_429: int = 3
    llm_retry_backoff_base_s: float = 2.0
    llm_retry_max_5xx: int = 2
    llm_retry_backoff_5xx_s: float = 1.0

    # Circuit breaker
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout_s: int = 60

    # Token truncation
    token_truncation_keep_last_n: int = 20

    # Token tracking
    token_tracking_enabled: bool = True


# Singleton
settings = Settings()
