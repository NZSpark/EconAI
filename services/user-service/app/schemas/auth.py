"""Auth request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1)
    provider: str = Field(default="local")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"


class GroupInfo(BaseModel):
    group_id: str
    name: str
    role: str


class UserInfo(BaseModel):
    user_id: str
    username: str
    display_name: str | None = None
    role: str
    groups: list[GroupInfo] = Field(default_factory=list)
    force_password_change: bool = False


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: UserInfo


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    user_id: str
    username: str
    display_name: str | None
    email: str | None
    role: str
    auth_provider: str
    is_active: bool
    force_password_change: bool
    groups: list[GroupInfo]


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)
