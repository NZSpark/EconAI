"""PolicyAI 用户与权限服务（M8）— 配置管理。

Inherits common DB/Redis/JWT defaults from shared.config.AppSettings.
"""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict
from shared.config import AppSettings


class Settings(AppSettings):
    """应用配置（从环境变量加载）。"""

    model_config = SettingsConfigDict(
        env_prefix="USER_SERVICE_", env_file=".env", extra="ignore"
    )

    # ——— Application ———
    app_name: str = "PolicyAI User Service"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8007

    # ——— Database ———
    # 继承自 database_url @property from AppSettings (computed from postgres_* fields)
    # Use env vars: USER_SERVICE_POSTGRES_HOST, USER_SERVICE_POSTGRES_PORT, etc.

    # ——— JWT (jwt_secret, jwt_algorithm inherited from AppSettings) ———
    jwt_access_expire_minutes: int = 120
    jwt_refresh_expire_hours: int = 24

    # ——— Redis ———
    # 继承自 redis_url @property from AppSettings (computed from redis_* fields)
    # Use env vars: USER_SERVICE_REDIS_HOST, USER_SERVICE_REDIS_PORT, etc.
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
