"""Audit log query router (admin only, read-only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit_log import AuditLog
from app.schemas.audit import AuditLogListResponse, AuditLogResponse

router = APIRouter(prefix="/api/admin/audit-logs", tags=["admin-audit"])


def _require_system_admin(request: Request) -> None:
    role = request.headers.get("X-User-Role") or getattr(request.state, "user_role", "")
    if role != "system_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "USER_PERMISSION_DENIED",
                    "message": "System admin required",
                }
            },
        )


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    user_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> AuditLogListResponse:
    _require_system_admin(request)

    query = select(AuditLog)
    count_query = select(func.count(AuditLog.id))

    if user_id:
        query = query.where(AuditLog.user_id == user_id)
        count_query = count_query.where(AuditLog.user_id == user_id)
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
