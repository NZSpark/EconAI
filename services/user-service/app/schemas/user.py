"""User management schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from shared.models import UserRole


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=128)
    email: str = Field(..., max_length=256)
    display_name: str | None = Field(None, max_length=256)
    password: str = Field(..., min_length=8)
    role: UserRole = Field(default=UserRole.analyst)
    # Group binding for project_admin (pick exactly one)
    group_id: str | None = Field(None, description="UUID of an existing group")
    group_name: str | None = Field(None, min_length=1, max_length=256, description="Name for a new group to create inline")

    @model_validator(mode="after")
    def _require_group_for_project_admin(self) -> "UserCreate":
        if self.role == UserRole.project_admin:
            if not self.group_id and not self.group_name:
                raise ValueError(
                    "project_admin role requires either 'group_id' (existing group) or 'group_name' (new group)"
                )
            if self.group_id and self.group_name:
                raise ValueError(
                    "Provide only one of 'group_id' or 'group_name', not both"
                )
        return self


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
    force_password_change: bool = False
    created_at: str | None = None


class AdminResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8)


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int
