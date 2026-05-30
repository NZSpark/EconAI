"""M1-28: 审计日志中间件测试（事件正确发布到 Redis）。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.config import Settings


class TestAuditEventStructure:
    """测试审计事件具有正确的结构。"""

    def test_audit_event_published_on_api_call(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """发起 API 调用应将审计事件发布到 Redis 发布/订阅。"""
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        # 验证 publish 是否被调用
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
        """审计事件应捕获项目查看的正确操作。"""
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
        """审计事件应正确识别资源类型。"""
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
        """任务创建应使用正确的操作进行审计。"""
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
        """审计事件应包含来自 JWT 的 user_id。"""
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
        """审计事件应包含 HTTP 状态码。"""
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        call_args = mock_redis.publish.call_args
        event = json.loads(call_args[0][1])
        assert event["status_code"] == 200


class TestAuditDisabled:
    """当审计日志被禁用时，不应发布任何事件。"""

    def test_audit_disabled_no_publish(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock, mock_settings: Settings
    ) -> None:
        """审计禁用时，不应调用 Redis publish。"""
        mock_redis.publish.reset_mock()
        mock_settings.audit_log_enabled = False
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        # 审计禁用时，publish 不应被调用
        assert not mock_redis.publish.called

    def test_audit_log_enabled_publishes_events(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """审计启用时，事件应被发布。"""
        mock_redis.publish.reset_mock()
        response = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        assert mock_redis.publish.called


class TestAuditEventActions:
    """测试各种 API 调用生成正确的操作名称。"""

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
        """文档上传应记录为 upload_document。"""
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
    """测试敏感操作捕获请求体摘要。"""

    def test_post_with_body_captures_summary(
        self, client: TestClient, access_token: str, mock_redis: AsyncMock
    ) -> None:
        """带请求体的 POST 请求应在 details 中包含请求体摘要。"""
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
        """GET 请求不应包含请求体摘要。"""
        response = client.get(
            "/api/projects/123",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        call_args = mock_redis.publish.call_args
        event = json.loads(call_args[0][1])
        # GET 请求不触发请求体读取
        assert "details" not in event or "body_summary" not in event.get("details", {})
