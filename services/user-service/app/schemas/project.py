"""项目管理数据模式。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=512)
    description: str | None = Field(None, max_length=4096)
    group_id: str


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=512)
    description: str | None = None


class ProjectResponse(BaseModel):
    project_id: str
    name: str
    description: str | None
    group_id: str
    owner_id: str
    status: str
    created_at: str | None = None


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
    page: int
    page_size: int
