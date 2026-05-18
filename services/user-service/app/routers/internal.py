"""Internal endpoints for service-to-service RBAC permission checks."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Project
from app.models.project_group import ProjectGroupMember
from app.models.user import User

router = APIRouter(prefix="/internal", tags=["internal"])


class PermissionCheckRequest(BaseModel):
    user_id: str
    project_id: str
    action: str  # view, create_task, upload_document, manage


class PermissionCheckResponse(BaseModel):
    allowed: bool
    reason: str | None = None


@router.get("/users/{user_id}/permissions")
async def get_user_permissions(
    user_id: str, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    group_result = await db.execute(
        select(ProjectGroupMember.group_id).where(
            ProjectGroupMember.user_id == uuid.UUID(user_id)
        )
    )
    group_ids = [str(r[0]) for r in group_result.all()]

    project_result = await db.execute(
        select(Project.id).where(
            Project.group_id.in_([uuid.UUID(g) for g in group_ids])
        )
    )
    project_ids = [str(r[0]) for r in project_result.all()]

    return {
        "user_id": str(user.id),
        "role": user.role,
        "group_ids": group_ids,
        "project_ids": project_ids,
    }


@router.post("/permissions/check", response_model=PermissionCheckResponse)
async def check_permission(
    body: PermissionCheckRequest, db: AsyncSession = Depends(get_db)
) -> PermissionCheckResponse:
    result = await db.execute(select(User).where(User.id == uuid.UUID(body.user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        return PermissionCheckResponse(allowed=False, reason="User not found")

    if not user.is_active:
        return PermissionCheckResponse(allowed=False, reason="User is inactive")

    # System admin has full access
    if user.role == "system_admin":
        return PermissionCheckResponse(allowed=True)

    # Check project membership
    project_result = await db.execute(
        select(Project).where(Project.id == uuid.UUID(body.project_id))
    )
    project = project_result.scalar_one_or_none()
    if project is None:
        return PermissionCheckResponse(allowed=False, reason="Project not found")

    # Check if user is in the project's group
    member_result = await db.execute(
        select(ProjectGroupMember).where(
            ProjectGroupMember.group_id == project.group_id,
            ProjectGroupMember.user_id == uuid.UUID(body.user_id),
        )
    )
    if member_result.scalar_one_or_none() is None:
        return PermissionCheckResponse(
            allowed=False, reason="User not in project group"
        )

    # Action-based checks
    if body.action == "manage" and user.role not in ("project_admin", "system_admin"):
        return PermissionCheckResponse(
            allowed=False, reason="Insufficient role for management"
        )

    return PermissionCheckResponse(allowed=True)
