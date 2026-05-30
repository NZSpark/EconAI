"""Database models for citation persistence (M6-24, M6-25).

Implements:
  - Citation SQLAlchemy model with UUID primary key
  - Bulk insert of verified citations
  - Query by task_output_id, with confidence filtering
  - Optional DB dependency (in-memory fallback for tests)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# ---------------------------------------------------------------------------
# SQLAlchemy base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Declarative base for SQLAlchemy models."""


# ---------------------------------------------------------------------------
# M6-24: Citation table
# ---------------------------------------------------------------------------


class Citation(Base):
    """Persisted citation record."""

    __tablename__ = "citations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_output_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ref_id: Mapped[str] = mapped_column(String(500), nullable=False)
    sentence: Mapped[str] = mapped_column(Text, nullable=False)
    sentence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    chunk_ids: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    page_ranges: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    verified_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    def __repr__(self) -> str:
        return f"<Citation id={self.id} ref_id={self.ref_id} confidence={self.confidence}>"


# ---------------------------------------------------------------------------
# M6-24: Bulk insert
# ---------------------------------------------------------------------------


async def bulk_insert(
    session: AsyncSession,
    citations_data: list[dict[str, Any]],
) -> list[Citation]:
    """插入 a batch of citation records.

    Args:
        session: An active async SQLAlchemy session.
        citations_data: List of dicts with Citation field values.

    Returns:
        List of persisted Citation objects.
    """
    records = [Citation(**data) for data in citations_data]
    session.add_all(records)
    await session.flush()
    return records


# ---------------------------------------------------------------------------
# M6-25: Query functions
# ---------------------------------------------------------------------------


async def get_by_task_output_id(
    session: AsyncSession,
    task_output_id: str,
    confidence: str | None = None,
) -> list[Citation]:
    """Query citations for a given task output, optionally filtered by confidence.

    Args:
        session: An active async SQLAlchemy session.
        task_output_id: The task output ID to look up.
        confidence: Optional confidence level filter (direct/fuzzy/uncertain).

    Returns:
        List of matching Citation objects.
    """
    stmt = select(Citation).where(Citation.task_output_id == task_output_id)
    if confidence:
        stmt = stmt.where(Citation.confidence == confidence)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_id(
    session: AsyncSession,
    citation_id: uuid.UUID,
) -> Citation | None:
    """Query a single citation by its UUID.

    Args:
        session: An active async SQLAlchemy session.
        citation_id: UUID of the citation record.

    Returns:
        Citation object or None if not found.
    """
    stmt = select(Citation).where(Citation.id == citation_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Optional engine / session factory
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None


async def get_engine(database_url: str | None = None) -> AsyncEngine | None:
    """创建 or retrieve the async engine.

    Returns None if no DATABASE_URL is configured (in-memory mode).
    """
    global _engine
    if _engine is not None:
        return _engine
    if database_url is None:
        return None
    _engine = create_async_engine(database_url, echo=False)
    return _engine


async def create_tables(engine: AsyncEngine) -> None:
    """创建 all tables if they do not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
