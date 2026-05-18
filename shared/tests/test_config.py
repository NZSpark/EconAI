"""Tests for shared config loader."""

from __future__ import annotations

from unittest.mock import patch

from shared.config import AppSettings


class TestAppSettings:
    def test_defaults(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = AppSettings()
            assert settings.environment == "development"
            assert settings.debug is False
            assert settings.postgres_host == "localhost"

    def test_database_url(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = AppSettings(
                postgres_host="db.example.com",
                postgres_port=5432,
                postgres_db="testdb",
                postgres_user="testuser",
                postgres_password="secret",
            )
            url = settings.database_url
            assert "db.example.com" in url
            assert "testdb" in url
            assert "testuser" in url

    def test_redis_url(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = AppSettings(
                redis_host="redis.local", redis_port=6379, redis_password="pwd"
            )
            assert settings.redis_url == "redis://:pwd@redis.local:6379"

    def test_env_override(self) -> None:
        with patch.dict(
            "os.environ",
            {"POSTGRES_HOST": "override-host", "DEBUG": "true"},
            clear=True,
        ):
            settings = AppSettings()
            assert settings.postgres_host == "override-host"
            assert settings.debug is True

    def test_extra_fields_allowed(self) -> None:
        """Extra fields should be allowed (extra=allow)."""
        settings = AppSettings(some_custom_key="value")  # type: ignore[call-arg]
        assert settings.some_custom_key == "value"  # type: ignore[attr-defined]
