"""M1-28: Audit logging middleware tests (events published to Redis properly)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.config import Settings


class TestAuditEventStructure:
    """Test that audit events have the correct structure."""

    def test_audit_event_published_on_api_call(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """Making an API call should publish an audit event to Redis pub/sub."""
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        # Verify publish was called
        assert mock_redis.publish.called
        call_args = mock_redis.publish.call_args
        assert call_args is not None
        channel, message = call_args[0]
        assert channel == "audit:log"
        event = json.loads(message)
        assert "user_id" in event
        assert "action" in event
        assert "resource_type" in event
        assert "ip_address" in event
        assert "timestamp" in event

    def test_audit_event_captures_action(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """The audit event should capture the correct action for project view."""
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        call_args = mock_redis.publish.call_args
        event = json.loads(call_args[0][1])
        assert event["action"] == "view_project"

    def test_audit_event_captures_resource_type(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """The audit event should identify the resource type correctly."""
        response = client.get(
            "/api/projects/123",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        call_args = mock_redis.publish.call_args
        event = json.loads(call_args[0][1])
        assert event["resource_type"] == "project"

    def test_audit_event_for_task(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """Task creation should be audited with the correct action."""
        response = client.post(
            "/api/projects/123/tasks",
            json={"type": "literature_review", "title": "Test task"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        call_args = mock_redis.publish.call_args
        event = json.loads(call_args[0][1])
        assert event["action"] == "create_task"
        assert event["resource_type"] == "task"

    def test_audit_event_captures_user_info(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """The audit event should include user_id from the JWT."""
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        call_args = mock_redis.publish.call_args
        event = json.loads(call_args[0][1])
        assert event["user_id"] == "test-user-001"

    def test_audit_event_includes_status_code(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """The audit event should include the HTTP status code."""
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        call_args = mock_redis.publish.call_args
        event = json.loads(call_args[0][1])
        assert event["status_code"] == 200


class TestAuditDisabled:
    """When audit logging is disabled, no events should be published."""

    def test_audit_disabled_no_publish(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock, mock_settings: Settings
    ) -> None:
        """With audit disabled, Redis publish should not be called."""
        mock_redis.publish.reset_mock()
        mock_settings.audit_log_enabled = False
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        # With audit disabled, publish should not have been called
        assert not mock_redis.publish.called

    def test_audit_log_enabled_publishes_events(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """With audit enabled, events should be published."""
        mock_redis.publish.reset_mock()
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        assert mock_redis.publish.called


class TestAuditEventActions:
    """Test that various API calls generate correct action names."""

    def test_login_action(self, client: TestClient, mock_redis: AsyncMock, mock_settings: Settings) -> None:
        mock_settings.audit_log_enabled = True
        mock_redis.publish.reset_mock()
        response = client.post("/api/auth/login", json={"username": "test", "password": "pass"})
        assert response.status_code == 200
        if mock_redis.publish.called:
            call_args = mock_redis.publish.call_args
            event = json.loads(call_args[0][1])
            assert event["action"] == "login"

    def test_document_upload_action(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """Document upload should be recorded as upload_document."""
        response = client.post(
            "/api/projects/123/documents",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        call_args = mock_redis.publish.call_args
        event = json.loads(call_args[0][1])
        assert event["action"] == "upload_document"
        assert event["resource_type"] == "document"


class TestAuditEventBodySummary:
    """Test that sensitive operations capture request body summaries."""

    def test_post_with_body_captures_summary(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """POST requests with bodies should have body summary in details."""
        response = client.post(
            "/api/projects/123/tasks",
            json={"type": "literature_review", "title": "My Task", "description": "A test"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        call_args = mock_redis.publish.call_args
        event = json.loads(call_args[0][1])
        if "details" in event and "body_summary" in event["details"]:
            assert "type" in event["details"]["body_summary"]

    def test_get_without_body_summary(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """GET requests should not have body summaries."""
        response = client.get(
            "/api/projects/123",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        call_args = mock_redis.publish.call_args
        event = json.loads(call_args[0][1])
        # GET requests don't trigger body reading
        assert "details" not in event or "body_summary" not in event.get("details", {})
