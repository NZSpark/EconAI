"""Admin user management router."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project_group import ProjectGroup, ProjectGroupMember
from app.models.user import User
from app.schemas.user import AdminResetPasswordRequest, UserCreate, UserListResponse, UserResponse, UserUpdate
from app.services.auth_service import hash_password
from shared.models import UserRole

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


def _require_admin(request: Request) -> None:
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


def _get_caller_role(request: Request) -> str:
    """Extract the caller's role from the request."""
    return request.headers.get("X-User-Role") or getattr(request.state, "user_role", "")


def _get_caller_id(request: Request) -> str:
    """Extract the caller's user ID from the request."""
    return request.headers.get("X-User-ID") or getattr(request.state, "user_id", "")


async def _get_caller_group_ids(request: Request, db: AsyncSession) -> list[str]:
    """Get group IDs the caller belongs to. Empty = system_admin (no filter)."""
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


# Roles that require system_admin to assign (privilege escalation check)
PRIVILEGED_ROLES = {"system_admin"}


def _check_role_escalation(caller_role: str, target_role: str) -> None:
    """Reject if caller tries to assign a role they are not privileged to grant."""
    if target_role in PRIVILEGED_ROLES and caller_role not in PRIVILEGED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "USER_ROLE_ESCALATION",
                    "message": f"Cannot assign role '{target_role}': insufficient privileges",
                }
            },
        )


async def _resolve_group_id(
    db: AsyncSession, body: UserCreate
) -> uuid.UUID:
    """Resolve group_id from body: existing group or inline-created group."""
    if body.group_id:
        # Verify the group exists
        result = await db.execute(
            select(ProjectGroup).where(ProjectGroup.id == uuid.UUID(body.group_id))
        )
        grp = result.scalar_one_or_none()
        if grp is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "GROUP_NOT_FOUND",
                        "message": f"Group '{body.group_id}' not found",
                    }
                },
            )
        return uuid.UUID(body.group_id)

    # Inline group creation
    grp = ProjectGroup(
        id=uuid.uuid4(),
        name=body.group_name,
        description=f"Auto-created for project_admin {body.username}",
    )
    db.add(grp)
    await db.flush()
    return grp.id


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    _require_admin(request)
    _check_role_escalation(_get_caller_role(request), body.role.value)

    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "USER_ALREADY_EXISTS",
                    "message": "Username already exists",
                }
            },
        )

    user = User(
        id=uuid.uuid4(),
        username=body.username,
        email=body.email,
        display_name=body.display_name,
        role=body.role,
        hashed_password=hash_password(body.password),
        auth_provider="local",
        is_active=True,
    )
    db.add(user)
    await db.flush()

    # Bind project_admin to a group (existing or newly created)
    if body.role == UserRole.project_admin:
        target_group_id = await _resolve_group_id(db, body)
        db.add(
            ProjectGroupMember(
                group_id=target_group_id,
                user_id=user.id,
                role="admin",  # group-level admin role
            )
        )
        await db.flush()

    # Auto-bind to caller's groups: when a project_admin creates any
    # lower-role user (analyst, senior_researcher), add the new user to
    # the project_admin's own groups so they appear in the scoped user list.
    caller_role = _get_caller_role(request)
    if caller_role == "project_admin" and body.role != UserRole.project_admin:
        caller_id = _get_caller_id(request)
        if caller_id:
            caller_groups_result = await db.execute(
                select(ProjectGroupMember.group_id, ProjectGroupMember.role).where(
                    ProjectGroupMember.user_id == uuid.UUID(caller_id)
                )
            )
            for group_id, _group_role in caller_groups_result.all():
                existing = await db.execute(
                    select(ProjectGroupMember).where(
                        ProjectGroupMember.group_id == group_id,
                        ProjectGroupMember.user_id == user.id,
                    )
                )
                if existing.scalar_one_or_none() is None:
                    db.add(
                        ProjectGroupMember(
                            group_id=group_id,
                            user_id=user.id,
                            role=body.role.value,
                        )
                    )
            await db.flush()

    return UserResponse(
        user_id=str(user.id),
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        auth_provider=user.auth_provider,
        is_active=user.is_active,
        force_password_change=user.force_password_change,
    )


@router.get("", response_model=UserListResponse)
async def list_users(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    role: str | None = None,
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    """List users — system_admin sees all; project_admin sees only users in their groups."""
    _require_admin(request)

    caller_role = _get_caller_role(request)
    caller_group_ids = await _get_caller_group_ids(request, db)

    query = select(User)
    count_query = select(func.count(User.id))

    # Group scoping: project_admin can only see users in their groups
    if caller_role != "system_admin" and caller_group_ids:
        # Subquery: user_ids in caller's groups
        subq = select(ProjectGroupMember.user_id).where(
            ProjectGroupMember.group_id.in_(
                [uuid.UUID(gid) for gid in caller_group_ids]
            )
        )
        query = query.where(User.id.in_(subq))
        count_query = count_query.where(User.id.in_(subq))
    elif caller_role != "system_admin" and not caller_group_ids:
        # project_admin with no groups → can't see any users
        return UserListResponse(items=[], total=0, page=page, page_size=page_size)

    if role:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
        count_query = count_query.where(User.is_active == is_active)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.offset((page - 1) * page_size).limit(page_size)
    users = (await db.execute(query)).scalars().all()

    return UserListResponse(
        items=[
            UserResponse(
                user_id=str(u.id),
                username=u.username,
                email=u.email,
                display_name=u.display_name,
                role=u.role,
                auth_provider=u.auth_provider,
                is_active=u.is_active,
                force_password_change=u.force_password_change,
            )
            for u in users
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    _require_admin(request)

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # Group scoping check: project_admin can only update users in their groups
    caller_role = _get_caller_role(request)
    if caller_role != "system_admin":
        caller_group_ids = await _get_caller_group_ids(request, db)
        if caller_group_ids:
            member_check = await db.execute(
                select(ProjectGroupMember).where(
                    ProjectGroupMember.user_id == uuid.UUID(user_id),
                    ProjectGroupMember.group_id.in_(
                        [uuid.UUID(gid) for gid in caller_group_ids]
                    ),
                )
            )
            if not member_check.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": {
                            "code": "USER_GROUP_OUT_OF_SCOPE",
                            "message": "You do not have access to this user",
                        }
                    },
                )

    if body.display_name is not None:
        user.display_name = body.display_name
    if body.role is not None:
        _check_role_escalation(_get_caller_role(request), body.role.value)
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active

    await db.flush()

    return UserResponse(
        user_id=str(user.id),
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        auth_provider=user.auth_provider,
        is_active=user.is_active,
        force_password_change=user.force_password_change,
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    _require_system_admin(request)

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    user.is_active = False
    await db.flush()


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: str,
    body: AdminResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Admin resets a user's password. Forces password change on next login."""
    _require_admin(request)

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # LDAP users cannot have password reset
    if user.auth_provider != "local":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "AUTH_LDAP_PASSWORD",
                    "message": "Cannot reset password for LDAP users",
                }
            },
        )

    # Group scoping: project_admin can only reset users in their groups
    caller_role = _get_caller_role(request)
    if caller_role != "system_admin":
        caller_group_ids = await _get_caller_group_ids(request, db)
        if caller_group_ids:
            member_check = await db.execute(
                select(ProjectGroupMember).where(
                    ProjectGroupMember.user_id == uuid.UUID(user_id),
                    ProjectGroupMember.group_id.in_(
                        [uuid.UUID(gid) for gid in caller_group_ids]
                    ),
                )
            )
            if not member_check.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": {
                            "code": "USER_GROUP_OUT_OF_SCOPE",
                            "message": "You do not have access to this user",
                        }
                    },
                )

    user.hashed_password = hash_password(body.new_password)
    user.force_password_change = True
    await db.flush()
