"""Audit log schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    audit_id: str
    user_id: str | None
    group_id: str | None = None
    action: str
    resource_type: str | None
    resource_id: str | None
    details: dict[str, Any] | None
    ip_address: str | None
    user_agent: str | None
    created_at: str | None


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
