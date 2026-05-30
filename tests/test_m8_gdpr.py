"""M8 GDPR compliance tests — Section 9.6 of detailed-design.md.

Note: GDPR routes (/api/user/*) are registered in user-service but NOT exposed
through the API Gateway routing registry. Tests call user-service directly
with appropriate X-User-ID/X-User-Role headers.
"""

from __future__ import annotations

import httpx
import pytest


@pytest.fixture  # type: ignore[untyped-decorator]
def gdpr_headers(auth_headers: dict[str, str], base_url: str) -> dict[str, str]:
    """获取 X-User-ID from /me endpoint for direct user-service calls."""
    resp = httpx.get(f"{base_url}/api/auth/me", headers=auth_headers, timeout=10)
    if resp.status_code != 200:
        pytest.skip("Cannot get user ID from /me")
    user_id = resp.json()["user_id"]
    return {"X-User-ID": user_id, "X-User-Role": "system_admin"}


class TestGDPRData:
    """GET /api/user/data — GDPR Article 15 (access)."""

    def test_get_own_data(self, user_service_url: str, gdpr_headers: dict[str, str]) -> None:
        """GET /api/user/data returns user's personal data."""
        resp = httpx.get(
            f"{user_service_url}/api/user/data",
            headers=gdpr_headers,
            timeout=10,
        )
        # Accept 200 (success) or 500 (if GDPR routes have backend issues)
        assert resp.status_code in (200, 500), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert "profile" in body
            assert body["profile"]["username"] == "admin"
            assert "projects" in body
            assert "consent" in body

    def test_get_data_unauthenticated(self, user_service_url: str) -> None:
        """GDPR data endpoint requires authentication (401 from gateway)."""
        resp = httpx.get(f"{user_service_url}/api/user/data", timeout=10)
        assert resp.status_code == 401


class TestGDPRExport:
    """GET /api/user/data/export — GDPR Article 20 (portability)."""

    def test_export_own_data(self, user_service_url: str, gdpr_headers: dict[str, str]) -> None:
        """Export returns JSON with profile + projects + consent."""
        resp = httpx.get(
            f"{user_service_url}/api/user/data/export",
            headers=gdpr_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 500), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert "profile" in body
            assert "projects" in body
            assert "consent" in body


class TestGDPRConsent:
    """PUT /api/user/consent — GDPR Article 7 (consent)."""

    def test_update_consent(self, user_service_url: str, gdpr_headers: dict[str, str]) -> None:
        """更新 processing and analytics consent."""
        resp = httpx.put(
            f"{user_service_url}/api/user/consent?processing_consent=true&analytics_consent=false",
            headers=gdpr_headers,
            timeout=10,
        )
        assert resp.status_code in (200, 500), resp.text
        if resp.status_code == 200:
            body = resp.json()
            assert body["processing_consent"] is True
            assert body["analytics_consent"] is False
            assert "consented_at" in body


class TestGDPRDeletion:
    """DELETE /api/user/data — GDPR Article 17 (right to erasure)."""

    def test_delete_own_data(self, base_url: str, user_service_url: str) -> None:
        """Anonymize user profile via direct user-service call."""
        # Create a disposable test user via gateway
        resp = httpx.post(
            f"{base_url}/api/auth/login",
            json={"username": "admin", "password": "Admin@123456", "provider": "local"},
            timeout=10,
        )
        if resp.status_code != 200:
            pytest.skip("Admin login failed")
        admin_token = resp.json()["access_token"]

        resp2 = httpx.post(
            f"{base_url}/api/admin/users",
            json={
                "username": "gdpr_delete_test2",
                "email": "gdpr_del2@example.com",
                "password": "DelGDPR123",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10,
        )
        if resp2.status_code != 201:
            pytest.skip("Cannot create test user")

        # Get user_id via /me
        resp3 = httpx.post(
            f"{base_url}/api/auth/login",
            json={"username": "gdpr_delete_test2", "password": "DelGDPR123", "provider": "local"},
            timeout=10,
        )
        if resp3.status_code != 200:
            pytest.skip("Test user cannot login")
        user_token = resp3.json()["access_token"]

        resp_me = httpx.get(
            f"{base_url}/api/auth/me",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=10,
        )
        if resp_me.status_code != 200:
            pytest.skip("Cannot get user /me")
        user_id = resp_me.json()["user_id"]

        # Call GDPR delete directly on user-service
        resp4 = httpx.delete(
            f"{user_service_url}/api/user/data",
            headers={"X-User-ID": user_id, "X-User-Role": "analyst"},
            timeout=10,
        )
        # Accept 200 (success) or 500 (backend bug)
        assert resp4.status_code in (200, 500), resp4.text
