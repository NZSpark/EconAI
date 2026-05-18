"""GDPR compliance router: data access, deletion, portability, consent."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.consent import UserConsent
from app.models.project import Project
from app.models.user import User

router = APIRouter(prefix="/api/user", tags=["gdpr"])


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


@router.get("/data")
async def get_user_data(
    request: Request, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    user_id = _get_user_id(request)
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    projects_result = await db.execute(
        select(Project).where(Project.created_by == user_id)
    )
    user_projects = projects_result.scalars().all()

    consent_result = await db.execute(
        select(UserConsent).where(UserConsent.user_id == user_id)
    )
    consent = consent_result.scalar_one_or_none()

    return {
        "profile": {
            "user_id": str(user.id),
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "auth_provider": user.auth_provider,
            "is_active": user.is_active,
        },
        "projects": [
            {"project_id": str(p.id), "name": p.name, "status": p.status}
            for p in user_projects
        ],
        "consent": {
            "processing_consent": consent.processing_consent if consent else False,
            "analytics_consent": consent.analytics_consent if consent else False,
            "consented_at": str(consent.consented_at)
            if consent and consent.consented_at
            else None,
        },
    }


@router.delete("/data")
async def delete_user_data(
    request: Request, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    user_id = _get_user_id(request)
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # Cascade delete user's projects
    projects_result = await db.execute(
        select(Project).where(Project.created_by == user_id)
    )
    for project in projects_result.scalars().all():
        await db.delete(project)

    # Remove consent records
    consent_result = await db.execute(
        select(UserConsent).where(UserConsent.user_id == user_id)
    )
    if consent := consent_result.scalar_one_or_none():
        await db.delete(consent)

    # Anonymize user profile
    user.username = f"deleted_{user.id}"
    user.email = f"anonymized_{user.id}@deleted.local"
    user.display_name = None
    user.hashed_password = None
    user.is_active = False

    await db.flush()
    return {"status": "deleted"}


@router.get("/data/export")
async def export_user_data(
    request: Request, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    return await get_user_data(request, db)


@router.put("/consent")
async def update_consent(
    request: Request,
    db: AsyncSession = Depends(get_db),
    processing_consent: bool = False,
    analytics_consent: bool = False,
) -> dict[str, Any]:
    user_id = _get_user_id(request)

    result = await db.execute(select(UserConsent).where(UserConsent.user_id == user_id))
    consent = result.scalar_one_or_none()

    if consent is None:
        consent = UserConsent(user_id=user_id)
        db.add(consent)

    consent.processing_consent = processing_consent
    consent.analytics_consent = analytics_consent
    consent.consented_at = datetime.now(UTC)
    await db.flush()

    return {
        "processing_consent": consent.processing_consent,
        "analytics_consent": consent.analytics_consent,
        "consented_at": str(consent.consented_at),
    }
