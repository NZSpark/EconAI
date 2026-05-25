"""Orchestration Service configuration via pydantic-settings."""

from functools import lru_cache

from shared.config import AppSettings


class OrchestrationSettings(AppSettings):
    """Task Orchestration Service configuration — inherits common DB/Redis/JWT from AppSettings."""

    # Service identity
    service_name: str = "orchestration-service"
    service_port: int = 8003

    # Override parent computed properties with direct defaults for Docker compatibility
    database_url: str = "postgresql+asyncpg://econai:econai_secret_change_me@localhost:5432/econai"
    redis_url: str = "redis://localhost:6379/0"
    celery_orchestration_queue: str = "orchestration"

    # Agent limits
    agent_max_iterations: int = 5
    agent_tool_timeout_s: int = 60
    agent_max_retrieved_chunks: int = 30
    task_timeout_minutes: int = 30

    # Dependent service URLs
    llm_router_url: str = "http://llm-router:8004"
    kb_service_url: str = "http://kb-service:8002"
    citation_service_url: str = "http://citation-service:8005"
    output_service_url: str = "http://output-service:8006"

    # Prompt templates (canonical location: repo root templates/prompts/)
    prompt_templates_dir: str = "templates/prompts"

    # Default output formats
    default_output_formats: list[str] = ["md", "docx"]

    model_config = {"case_sensitive": False, "env_prefix": "ORCH_"}


@lru_cache
def get_settings() -> OrchestrationSettings:
    return OrchestrationSettings()


settings = get_settings()
