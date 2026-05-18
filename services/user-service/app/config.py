"""EconAI User & Permission Service (M8) — configuration management."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_prefix="USER_SERVICE_", env_file=".env", extra="ignore"
    )

    # ——— Application ———
    app_name: str = "EconAI User Service"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8007

    # ——— Database ———
    database_url: str = "postgresql+asyncpg://econai:econai@localhost:5432/econai"
    database_url_sync: str = "postgresql+psycopg2://econai:econai@localhost:5432/econai"

    # ——— JWT ———
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 120
    jwt_refresh_expire_hours: int = 24

    # ——— Redis ———
    redis_url: str = "redis://localhost:6379/0"
    token_blacklist_enabled: bool = True

    # ——— LDAP ———
    ldap_enabled: bool = False
    ldap_server: str = "ldap://localhost:389"
    ldap_base_dn: str = "dc=institution,dc=cn"
    ldap_user_filter: str = "(uid=%(username)s)"
    ldap_group_mapping: dict[str, str] = {}
    ldap_pool_size: int = 4
    ldap_timeout_seconds: int = 10

    # ——— Audit ———
    audit_log_retention_months: int = 6
    audit_log_enabled: bool = True

    # ——— Bcrypt ———
    bcrypt_rounds: int = 12

    @property
    def jwt_access_expire_seconds(self) -> int:
        return self.jwt_access_expire_minutes * 60

    @property
    def jwt_refresh_expire_seconds(self) -> int:
        return self.jwt_refresh_expire_hours * 3600


settings = Settings()
