"""从环境变量加载的 API 网关配置。"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量和 .env 文件加载的应用配置。"""

    model_config = SettingsConfigDict(
        env_prefix="API_GATEWAY_", env_file=".env", extra="ignore"
    )

    # ——— 应用 ———
    app_name: str = "PolicyAI API Gateway"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # ——— JWT ———
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 120
    jwt_refresh_expire_hours: int = 24

    # ——— Redis ———
    redis_url: str = "redis://localhost:6379/0"
    token_blacklist_enabled: bool = True

    # ——— 速率限制 ———
    rate_limit_enabled: bool = True
    rate_limit_per_user: int = 100
    rate_limit_per_ip: int = 300
    rate_limit_upload: int = 20
    rate_limit_task_create: int = 10

    # ——— 审计 ———
    audit_log_enabled: bool = True

    # ——— CORS ———
    cors_origins: str = '["*"]'

    # ——— 请求 ———
    max_request_size_mb: int = 100

    # ——— 后端服务 ———
    user_service_url: str = "http://user-service:8007"
    document_service_url: str = "http://document-service:8001"
    kb_service_url: str = "http://kb-service:8002"
    orchestration_service_url: str = "http://orchestration-service:8003"
    llm_router_url: str = "http://llm-router:8004"
    citation_service_url: str = "http://citation-service:8005"
    output_service_url: str = "http://output-service:8006"

    # ——— 代理 ———
    proxy_timeout_s: float = 120.0
    proxy_max_retries: int = 2

    @property
    def jwt_access_expire_seconds(self) -> int:
        return self.jwt_access_expire_minutes * 60

    @property
    def jwt_refresh_expire_seconds(self) -> int:
        return self.jwt_refresh_expire_hours * 3600

    @property
    def max_request_size_bytes(self) -> int:
        return self.max_request_size_mb * 1024 * 1024

    @property
    def cors_origins_list(self) -> list[str]:
        import json
        from typing import cast

        return cast("list[str]", json.loads(self.cors_origins))


settings = Settings()
