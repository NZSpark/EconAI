"""。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Project
from app.models.project_group import ProjectGroupMember
from app.schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _get_user_id(request: Request) -> uuid.UUID:
    uid = request.headers.get("X-User-ID") or getattr(request.state, "user_id", None)
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "AUTH_TOKEN_MISSING",
                    "message": "Authentication required",
                }
            },
        )
    return uuid.UUID(uid)


async def _get_user_group_ids(db: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    result = await db.execute(
        select(ProjectGroupMember.group_id).where(ProjectGroupMember.user_id == user_id)
    )
    return [row[0] for row in result.all()]


async def _verify_project_access(
    db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID
) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    group_ids = await _get_user_group_ids(db, user_id)
    if project.group_id not in group_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {"code": "USER_PERMISSION_DENIED", "message": "Access denied"}
            },
        )
    return project


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    user_id = _get_user_id(request)
    target_group_id = uuid.UUID(body.group_id)

    # 验证 the user belongs to the target group
    group_ids = await _get_user_group_ids(db, user_id)
    if target_group_id not in group_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "USER_GROUP_OUT_OF_SCOPE",
                    "message": "You can only create projects in groups you belong to",
                }
            },
        )

    project = Project(
        id=uuid.uuid4(),
        name=body.name,
        description=body.description,
        group_id=target_group_id,
        created_by=user_id,
        status="active",
    )
    db.add(project)
    await db.flush()

    return ProjectResponse(
        project_id=str(project.id),
        name=project.name,
        description=project.description,
        group_id=str(project.group_id),
        owner_id=str(project.created_by),
        status=project.status,
        created_at=project.created_at.isoformat() if project.created_at else None,
    )



@router.get("", response_model=ProjectListResponse)
async def list_projects(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    status_filter: str | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> ProjectListResponse:
    user_id = _get_user_id(request)
    group_ids = await _get_user_group_ids(db, user_id)

    query = select(Project).where(Project.group_id.in_(group_ids))
    count_query = select(func.count(Project.id)).where(Project.group_id.in_(group_ids))

    if status_filter:
        query = query.where(Project.status == status_filter)
        count_query = count_query.where(Project.status == status_filter)

    if search:
        search_filter = Project.name.ilike(f"%{search}%")
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(Project.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    projects = (await db.execute(query)).scalars().all()

    return ProjectListResponse(
        items=[
            ProjectResponse(
                project_id=str(p.id),
                name=p.name,
                description=p.description,
                group_id=str(p.group_id),
                owner_id=str(p.created_by),
                status=p.status,
                created_at=p.created_at.isoformat() if p.created_at else None,
            )
            for p in projects
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    user_id = _get_user_id(request)
    project = await _verify_project_access(db, uuid.UUID(project_id), user_id)

    return ProjectResponse(
        project_id=str(project.id),
        name=project.name,
        description=project.description,
        group_id=str(project.group_id),
        owner_id=str(project.created_by),
        status=project.status,
        created_at=project.created_at.isoformat() if project.created_at else None,
    )



@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    user_id = _get_user_id(request)
    project = await _verify_project_access(db, uuid.UUID(project_id), user_id)

    if project.status == "archived":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "PROJECT_ARCHIVED",
                    "message": "Archived projects cannot be modified",
                }
            },
        )

    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    await db.flush()

    return ProjectResponse(
        project_id=str(project.id),
        name=project.name,
        description=project.description,
        group_id=str(project.group_id),
        owner_id=str(project.created_by),
        status=project.status,
        created_at=project.created_at.isoformat() if project.created_at else None,
    )



@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_project(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    user_id = _get_user_id(request)
    project = await _verify_project_access(db, uuid.UUID(project_id), user_id)
    project.status = "archived"
    await db.flush()
