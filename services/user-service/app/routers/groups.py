"""Project group management router."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project_group import ProjectGroup, ProjectGroupMember
from app.schemas.group import (
    GroupCreate,
    GroupMemberAdd,
    GroupMemberResponse,
    GroupResponse,
)

router = APIRouter(prefix="/api/admin/groups", tags=["admin-groups"])


def _require_project_admin(request: Request) -> None:
    role = request.headers.get("X-User-Role") or getattr(request.state, "user_role", "")
    if role not in ("project_admin", "system_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "USER_PERMISSION_DENIED",
                    "message": "Admin access required",
                }
            },
        )


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


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: GroupCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> GroupResponse:
    _require_system_admin(request)

    group = ProjectGroup(
        id=uuid.uuid4(),
        name=body.name,
        description=body.description,
    )
    db.add(group)
    await db.flush()

    return GroupResponse(
        group_id=str(group.id),
        name=group.name,
        description=group.description,
        member_count=0,
    )


@router.get("", response_model=list[GroupResponse])
async def list_groups(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> list[GroupResponse]:
    _require_project_admin(request)

    result = await db.execute(select(ProjectGroup))
    groups = result.scalars().all()

    return [
        GroupResponse(
            group_id=str(g.id),
            name=g.name,
            description=g.description,
            member_count=len(g.members) if g.members else 0,
        )
        for g in groups
    ]


@router.post("/{group_id}/members", response_model=GroupMemberResponse)
async def add_member(
    group_id: str,
    body: GroupMemberAdd,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> GroupMemberResponse:
    _require_project_admin(request)

    existing = await db.execute(
        select(ProjectGroupMember).where(
            ProjectGroupMember.group_id == uuid.UUID(group_id),
            ProjectGroupMember.user_id == uuid.UUID(body.user_id),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "MEMBER_ALREADY_EXISTS",
                    "message": "User is already a member",
                }
            },
        )

    member = ProjectGroupMember(
        group_id=uuid.UUID(group_id),
        user_id=uuid.UUID(body.user_id),
        role=body.role,
    )
    db.add(member)
    await db.flush()

    from app.models.user import User

    user_result = await db.execute(
        select(User).where(User.id == uuid.UUID(body.user_id))
    )
    user = user_result.scalar_one_or_none()

    return GroupMemberResponse(
        user_id=str(user.id) if user else body.user_id,
        username=user.username if user else "",
        display_name=user.display_name if user else None,
        role=body.role,
    )


@router.delete("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    group_id: str,
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    _require_project_admin(request)

    result = await db.execute(
        select(ProjectGroupMember).where(
            ProjectGroupMember.group_id == uuid.UUID(group_id),
            ProjectGroupMember.user_id == uuid.UUID(user_id),
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    await db.delete(member)
    await db.flush()
