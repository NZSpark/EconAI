"""Project group management router."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project_group import ProjectGroup, ProjectGroupMember
from app.schemas.group import (
    GroupCreate,
    GroupListResponse,
    GroupMemberAdd,
    GroupMemberResponse,
    GroupResponse,
)

router = APIRouter(prefix="/api/admin/groups", tags=["admin-groups"])


def _get_caller_role(request: Request) -> str:
    return request.headers.get("X-User-Role") or getattr(request.state, "user_role", "")


def _get_caller_id(request: Request) -> str:
    return request.headers.get("X-User-ID") or getattr(request.state, "user_id", "")


def _require_project_admin(request: Request) -> None:
    role = _get_caller_role(request)
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
    role = _get_caller_role(request)
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


async def _get_caller_group_ids(request: Request, db: AsyncSession) -> list[str]:
    """获取 group IDs visible to the caller. Returns all groups for system_admin."""
    role = _get_caller_role(request)
    if role == "system_admin":
        return []  # Empty = no filter (see all)

    user_id = _get_caller_id(request)
    if not user_id:
        return []

    result = await db.execute(
        select(ProjectGroupMember.group_id).where(
            ProjectGroupMember.user_id == uuid.UUID(user_id)
        )
    )
    return [str(row[0]) for row in result.all()]


def _check_group_access(group_id: str, caller_group_ids: list[str], is_system_admin: bool) -> None:
    """Raise 403 if caller cannot access the given group."""
    if is_system_admin or not caller_group_ids:
        return
    if group_id not in caller_group_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "USER_GROUP_OUT_OF_SCOPE",
                    "message": "You do not have access to this project group",
                }
            },
        )


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: GroupCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> GroupResponse:
    """创建 a project group — project_admin or system_admin."""
    _require_project_admin(request)

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
        created_at=group.created_at,
    )


@router.get("", response_model=GroupListResponse)
async def list_groups(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> GroupListResponse:
    """列出 groups — system_admin sees all; project_admin sees only their groups."""
    _require_project_admin(request)

    role = _get_caller_role(request)
    visible_ids = await _get_caller_group_ids(request, db)

    if role == "system_admin":
        count_q = select(func.count(ProjectGroup.id))
        q = select(ProjectGroup)
    else:
        if not visible_ids:
            return GroupListResponse(items=[], total=0, page=page, page_size=page_size)
        q = select(ProjectGroup).where(
            ProjectGroup.id.in_([uuid.UUID(gid) for gid in visible_ids])
        )
        count_q = select(func.count(ProjectGroup.id)).where(
            ProjectGroup.id.in_([uuid.UUID(gid) for gid in visible_ids])
        )

    total = (await db.execute(count_q)).scalar() or 0
    q = q.offset((page - 1) * page_size).limit(page_size)
    groups = (await db.execute(q)).scalars().all()

    return GroupListResponse(
        items=[
            GroupResponse(
                group_id=str(g.id),
                name=g.name,
                description=g.description,
                member_count=len(g.members) if g.members else 0,
                created_at=g.created_at,
            )
            for g in groups
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{group_id}/members", response_model=GroupMemberResponse)
async def add_member(
    group_id: str,
    body: GroupMemberAdd,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> GroupMemberResponse:
    _require_project_admin(request)

    role = _get_caller_role(request)
    visible_ids = await _get_caller_group_ids(request, db)
    _check_group_access(group_id, visible_ids, role == "system_admin")

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


@router.get("/{group_id}/members", response_model=list[GroupMemberResponse])
async def list_members(
    group_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> list[GroupMemberResponse]:
    """列出 members of a project group."""
    _require_project_admin(request)

    role = _get_caller_role(request)
    visible_ids = await _get_caller_group_ids(request, db)
    _check_group_access(group_id, visible_ids, role == "system_admin")

    from app.models.user import User

    result = await db.execute(
        select(ProjectGroupMember, User.username, User.display_name)
        .join(User, ProjectGroupMember.user_id == User.id)
        .where(ProjectGroupMember.group_id == uuid.UUID(group_id))
    )
    members = result.all()

    return [
        GroupMemberResponse(
            user_id=str(member.user_id),
            username=username,
            display_name=display_name,
            role=member.role,
        )
        for member, username, display_name in members
    ]


@router.get("/{group_id}/non-members", response_model=list[GroupMemberResponse])
async def list_non_members(
    group_id: str,
    request: Request,
    q: str = Query("", description="Search query for username/display_name"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[GroupMemberResponse]:
    """列出 users NOT in the group — for the add-member select."""
    _require_project_admin(request)

    role = _get_caller_role(request)
    visible_ids = await _get_caller_group_ids(request, db)
    _check_group_access(group_id, visible_ids, role == "system_admin")

    from app.models.user import User

    # Users already in this group
    member_subq = select(ProjectGroupMember.user_id).where(
        ProjectGroupMember.group_id == uuid.UUID(group_id)
    )

    q_users = select(User.id, User.username, User.display_name).where(
        User.is_active == True,
        User.id.not_in(member_subq),
    )

    if q:
        pattern = f"%{q}%"
        q_users = q_users.where(
            User.username.ilike(pattern) | User.display_name.ilike(pattern)
        )

    q_users = q_users.order_by(User.username).limit(limit)
    result = await db.execute(q_users)
    rows = result.all()

    return [
        GroupMemberResponse(
            user_id=str(row.id),
            username=row.username,
            display_name=row.display_name,
            role="",
        )
        for row in rows
    ]


@router.delete("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    group_id: str,
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    _require_project_admin(request)

    role = _get_caller_role(request)
    visible_ids = await _get_caller_group_ids(request, db)
    _check_group_access(group_id, visible_ids, role == "system_admin")

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
