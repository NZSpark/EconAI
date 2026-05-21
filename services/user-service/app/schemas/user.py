"""User management schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field
from shared.models import UserRole


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=128)
    email: str = Field(..., max_length=256)
    display_name: str | None = Field(None, max_length=256)
    password: str = Field(..., min_length=8)
    role: UserRole = Field(default=UserRole.analyst)


class UserUpdate(BaseModel):
    display_name: str | None = Field(None, max_length=256)
    role: UserRole | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    user_id: str
    username: str
    email: str | None
    display_name: str | None
    role: str
    auth_provider: str
    is_active: bool
    created_at: str | None = None


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int
