"""用户管理数据模式。"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from shared.models import UserRole


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=128)
    email: str = Field(..., max_length=256)
    display_name: str | None = Field(None, max_length=256)
    password: str = Field(..., min_length=8)
    role: UserRole = Field(default=UserRole.analyst)
    # project_admin 的组织绑定（二选一）
    group_id: str | None = Field(None, description="已有组织的 UUID")
    group_name: str | None = Field(None, min_length=1, max_length=256, description="要内联创建的新组织名称")

    @model_validator(mode="after")
    def _require_group_for_project_admin(self) -> "UserCreate":
        if self.role == UserRole.project_admin:
            if not self.group_id and not self.group_name:
                raise ValueError(
                    "project_admin 角色需要 'group_id'（已有组织）或 'group_name'（新组织）"
                )
            if self.group_id and self.group_name:
                raise ValueError(
                    "仅提供 'group_id' 或 'group_name' 之一，不要同时提供"
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
