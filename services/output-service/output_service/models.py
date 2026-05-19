"""Database models for task outputs (M7-05).

Implements task_outputs table CRUD operations.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for SQLAlchemy models."""


class TaskOutput(Base):
    """Persisted task output record."""

    __tablename__ = "task_outputs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    minio_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    citation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


async def create_output(
    session: AsyncSession,
    task_id: str,
    format_name: str,
    title: str | None = None,
    content: str | None = None,
    minio_path: str | None = None,
    citation_count: int = 0,
) -> TaskOutput:
    """Create a new task_output record."""
    output = TaskOutput(
        task_id=task_id,
        format=format_name,
        title=title,
        content=content,
        minio_path=minio_path,
        citation_count=citation_count,
    )
    session.add(output)
    await session.flush()
    return output


async def get_outputs_by_task(
    session: AsyncSession,
    task_id: str,
) -> list[TaskOutput]:
    """Get all outputs for a given task."""
    stmt = select(TaskOutput).where(TaskOutput.task_id == task_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_output_by_id(
    session: AsyncSession,
    output_id: uuid.UUID,
) -> TaskOutput | None:
    """Get a single output by its ID."""
    stmt = select(TaskOutput).where(TaskOutput.id == output_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def delete_outputs_by_task(
    session: AsyncSession,
    task_id: str,
) -> int:
    """Delete all outputs for a given task. Returns count of deleted rows."""
    from sqlalchemy import delete

    stmt = delete(TaskOutput).where(TaskOutput.task_id == task_id)
    result = await session.execute(stmt)
    await session.flush()
    return result.rowcount  # type: ignore[attr-defined, no-any-return]
