"""Celery worker entry point for the orchestration queue (M4-03).

In production, the Agent loop runs inside a Celery task with a 30-minute
soft time limit. For MVP/testing, the app.py uses asyncio.create_task instead.
"""

from __future__ import annotations

import asyncio
import logging

from celery import Celery
from celery.signals import task_failure, task_prerun

from orchestration_service.config import settings

logger = logging.getLogger(__name__)

app = Celery(
    "orchestration",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

app.conf.update(
    task_default_queue=settings.celery_orchestration_queue,
    task_soft_time_limit=settings.task_timeout_minutes * 60,
    task_time_limit=settings.task_timeout_minutes * 60 + 120,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


@app.task(name="orchestration.run_agent", bind=True)
def run_agent_task(self: object, task_id: str) -> dict[str, str]:
    """Celery task wrapper for the Agent loop."""
    logger.info("Celery task started for task_id=%s", task_id)

    from orchestration_service.app import _run_agent

    try:
        asyncio.get_event_loop().run_until_complete(_run_agent(task_id))
    except Exception:
        logger.exception("Celery task failed for task_id=%s", task_id)
        raise

    return {"task_id": task_id, "status": "completed"}


@task_prerun.connect
def on_task_prerun(task_id: str | None = None, task: object | None = None, **kwargs: object) -> None:
    logger.info("Celery task starting: %s", task_id)


@task_failure.connect
def on_task_failure(task_id: str | None = None, exception: Exception | None = None, **kwargs: object) -> None:
    logger.error("Celery task failed: %s — %s", task_id, exception)
