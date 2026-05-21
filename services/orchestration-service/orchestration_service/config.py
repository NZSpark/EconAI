"""Orchestration Service configuration via pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class OrchestrationSettings(BaseSettings):
    """Task Orchestration Service configuration."""

    # Service identity
    service_name: str = "orchestration-service"
    service_port: int = 8003

    # Database
    database_url: str = "postgresql+asyncpg://econai:econai_secret_change_me@localhost:5432/econai"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_orchestration_queue: str = "orchestration"

    # Agent limits
    agent_max_iterations: int = 5
    agent_tool_timeout_s: int = 60
    agent_max_retrieved_chunks: int = 30
    task_timeout_minutes: int = 30

    # Dependent service URLs
    llm_router_url: str = "http://localhost:8004"
    kb_service_url: str = "http://localhost:8002"
    citation_service_url: str = "http://localhost:8005"
    output_service_url: str = "http://localhost:8006"

    # Prompt templates (canonical location: repo root templates/prompts/)
    prompt_templates_dir: str = "templates/prompts"

    # Default output formats
    default_output_formats: list[str] = ["md", "docx"]

    model_config = {"env_prefix": "ORCH_", "case_sensitive": False}


@lru_cache
def get_settings() -> OrchestrationSettings:
    return OrchestrationSettings()


settings = get_settings()
