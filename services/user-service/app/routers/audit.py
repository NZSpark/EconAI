"""Audit log query router (admin only, read-only, group-scoped)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.project_group import ProjectGroupMember
from app.schemas.audit import AuditLogListResponse, AuditLogResponse

router = APIRouter(prefix="/api/admin/audit-logs", tags=["admin-audit"])


def _get_caller_role(request: Request) -> str:
    return request.headers.get("X-User-Role") or getattr(request.state, "user_role", "")


def _get_caller_id(request: Request) -> str:
    return request.headers.get("X-User-ID") or getattr(request.state, "user_id", "")


async def _get_caller_group_ids(request: Request, db: AsyncSession) -> list[str]:
    """获取 group IDs the caller belongs to."""
    role = _get_caller_role(request)
    if role == "system_admin":
        return []

    user_id = _get_caller_id(request)
    if not user_id:
        return []

    result = await db.execute(
        select(ProjectGroupMember.group_id).where(
            ProjectGroupMember.user_id == uuid.UUID(user_id)
        )
    )
    return [str(row[0]) for row in result.all()]


def _require_audit_access(request: Request) -> None:
    """Allow system_admin (all) or project_admin (their groups)."""
    role = _get_caller_role(request)
    if role not in ("project_admin", "system_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "USER_PERMISSION_DENIED",
                    "message": "Audit access requires admin privileges",
                }
            },
        )


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    user_id: str | None = None,
    group_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> AuditLogListResponse:
    """列出 audit logs — system_admin sees all; project_admin sees only their groups."""
    _require_audit_access(request)

    caller_role = _get_caller_role(request)
    caller_group_ids = await _get_caller_group_ids(request, db)

    query = select(AuditLog)
    count_query = select(func.count(AuditLog.id))

    # Group scoping: project_admin sees only audit logs from their groups
    if caller_role != "system_admin":
        if caller_group_ids:
            group_uuids = [uuid.UUID(gid) for gid in caller_group_ids]
            query = query.where(
                AuditLog.group_id.in_(group_uuids)
            )
            count_query = count_query.where(
                AuditLog.group_id.in_(group_uuids)
            )
        else:
            # project_admin with no groups → no audit logs
            return AuditLogListResponse(items=[], total=0, page=page, page_size=page_size)

    # Optional filters
    if user_id:
        query = query.where(AuditLog.user_id == uuid.UUID(user_id))
        count_query = count_query.where(AuditLog.user_id == uuid.UUID(user_id))
    if group_id:
        query = query.where(AuditLog.group_id == uuid.UUID(group_id))
        count_query = count_query.where(AuditLog.group_id == uuid.UUID(group_id))
    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
        count_query = count_query.where(AuditLog.resource_type == resource_type)
    if from_date:
        query = query.where(AuditLog.created_at >= from_date)
        count_query = count_query.where(AuditLog.created_at >= from_date)
    if to_date:
        query = query.where(AuditLog.created_at <= to_date)
        count_query = count_query.where(AuditLog.created_at <= to_date)

    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(AuditLog.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    logs = (await db.execute(query)).scalars().all()

    return AuditLogListResponse(
        items=[
            AuditLogResponse(
                audit_id=str(log.id),
                user_id=str(log.user_id) if log.user_id else None,
                group_id=str(log.group_id) if log.group_id else None,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=str(log.resource_id) if log.resource_id else None,
                details=log.details,
                ip_address=str(log.ip_address) if log.ip_address else None,
                user_agent=log.user_agent,
                created_at=str(log.created_at),
            )
            for log in logs
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
