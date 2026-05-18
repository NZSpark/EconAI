"""Project group schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str | None = None


class GroupMemberAdd(BaseModel):
    user_id: str
    role: str = Field(default="analyst")


class GroupResponse(BaseModel):
    group_id: str
    name: str
    description: str | None
    member_count: int = 0


class GroupMemberResponse(BaseModel):
    user_id: str
    username: str
    display_name: str | None
    role: str
