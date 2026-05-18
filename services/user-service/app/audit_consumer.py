"""Redis pub/sub consumer: listen on audit:log channel, write to audit_logs table."""

from __future__ import annotations

import asyncio
import json
import logging

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


async def audit_consumer(
    redis: Redis,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Run indefinitely, consuming audit events from Redis pub/sub."""
    pubsub = redis.pubsub()
    await pubsub.subscribe("audit:log")
    logger.info("Audit consumer started, listening on audit:log")

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            try:
                data = json.loads(message["data"])
            except (json.JSONDecodeError, TypeError):
                logger.warning("Invalid audit message: %s", message.get("data"))
                continue

            try:
                async with session_factory() as session:
                    audit_entry = AuditLog(
                        user_id=data.get("user_id"),
                        action=data.get("action", "unknown"),
                        resource_type=data.get("resource_type"),
                        resource_id=data.get("resource_id"),
                        details=data.get("details"),
                        ip_address=data.get("ip_address"),
                        user_agent=data.get("user_agent"),
                    )
                    session.add(audit_entry)
                    await session.commit()
            except Exception:
                logger.exception("Failed to persist audit log entry")
    except asyncio.CancelledError:
        logger.info("Audit consumer shutting down")
    finally:
        await pubsub.unsubscribe("audit:log")
