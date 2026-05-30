"""内部 API 路由 —— 供其他微服务调用的用户权限查询接口。

这些端点不暴露给前端，仅供内部服务间通信：
- /internal/users/{user_id}/permissions: 获取用户权限摘要
- /internal/permissions/check: 检查用户对某个项目的操作权限
"""

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
    """权限检查请求体。"""
    user_id: str
    project_id: str
    action: str  # view, create_task, upload_document, manage


class PermissionCheckResponse(BaseModel):
    """权限检查响应。"""
    allowed: bool
    reason: str | None = None


@router.get("/users/{user_id}/permissions")
async def get_user_permissions(
    user_id: str, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """获取用户的完整权限摘要（角色、所属组织、可访问项目）。
    
    供 orchestration-service 等内部服务调用，用于业务层权限判断。
    """
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # 查询用户所属的组织
    group_result = await db.execute(
        select(ProjectGroupMember.group_id).where(
            ProjectGroupMember.user_id == uuid.UUID(user_id)
        )
    )
    group_ids = [str(r[0]) for r in group_result.all()]

    # 查询用户可访问的项目
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
    """检查用户对某个项目是否有指定的操作权限。
    
    检查逻辑：
    1. 用户是否存在且激活
    2. system_admin 有全部权限
    3. 用户是否属于项目所在的组织
    4. 特定操作（manage）需要 project_admin 或以上角色
    """
    result = await db.execute(select(User).where(User.id == uuid.UUID(body.user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        return PermissionCheckResponse(allowed=False, reason="User not found")

    if not user.is_active:
        return PermissionCheckResponse(allowed=False, reason="User is inactive")

    # system_admin 拥有全部权限
    if user.role == "system_admin":
        return PermissionCheckResponse(allowed=True)

    # 检查项目是否存在
    project_result = await db.execute(
        select(Project).where(Project.id == uuid.UUID(body.project_id))
    )
    project = project_result.scalar_one_or_none()
    if project is None:
        return PermissionCheckResponse(allowed=False, reason="Project not found")

    # 检查用户是否属于项目所在的组织
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

    # 管理操作需要 project_admin 或 system_admin
    if body.action == "manage" and user.role not in ("project_admin", "system_admin"):
        return PermissionCheckResponse(
            allowed=False, reason="Insufficient role for management"
        )

    return PermissionCheckResponse(allowed=True)
