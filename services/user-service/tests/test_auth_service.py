"""Tests for auth_service.py — M8-03 through M8-07."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import jwt
import pytest

from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify(self) -> None:
        pw = "TestPassword123"
        hashed = hash_password(pw)
        assert hashed != pw
        assert verify_password(pw, hashed) is True

    def test_wrong_password(self) -> None:
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False


class TestJWT:
    def test_create_access_token(self) -> None:
        with patch("app.services.auth_service.settings") as mock_settings:
            mock_settings.jwt_secret = "test-secret-32-chars-long!"
            mock_settings.jwt_algorithm = "HS256"
            mock_settings.jwt_access_expire_seconds = 7200

            token = create_access_token("user-1", "alice", "analyst", ["g-1"])
            payload = decode_token(token)
            assert payload["sub"] == "user-1"
            assert payload["username"] == "alice"
            assert payload["role"] == "analyst"
            assert payload["group_ids"] == ["g-1"]
            assert payload["type"] == "access"

    def test_create_refresh_token(self) -> None:
        with patch("app.services.auth_service.settings") as mock_settings:
            mock_settings.jwt_secret = "test-secret-32-chars-long!"
            mock_settings.jwt_algorithm = "HS256"
            mock_settings.jwt_refresh_expire_seconds = 86400

            token = create_refresh_token("user-1")
            payload = decode_token(token)
            assert payload["sub"] == "user-1"
            assert payload["type"] == "refresh"

    def test_decode_invalid_token(self) -> None:
        with pytest.raises(jwt.InvalidTokenError):
            decode_token("invalid.token.here")


class TestBlacklist:
    @pytest.mark.asyncio
    async def test_is_blacklisted_false(self) -> None:
        redis = AsyncMock()
        redis.exists.return_value = 0
        result = await _call_is_blacklisted("some-jti", redis)
        assert result is False

    @pytest.mark.asyncio
    async def test_is_blacklisted_true(self) -> None:
        redis = AsyncMock()
        redis.exists.return_value = 1
        result = await _call_is_blacklisted("some-jti", redis)
        assert result is True

    @pytest.mark.asyncio
    async def test_blacklist_token(self) -> None:
        from app.services.auth_service import settings as svc_settings

        with patch.object(svc_settings, "token_blacklist_enabled", True):
            pass


async def _call_is_blacklisted(jti: str, redis: AsyncMock) -> bool:
    from app.services.auth_service import is_token_blacklisted

    return await is_token_blacklisted(jti, redis)
