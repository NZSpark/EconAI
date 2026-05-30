"""编排队列的 Celery worker 入口（M4-03）。

生产环境中，Agent 循环在 Celery 任务中运行，带有 30 分钟的软时间限制。
对于 MVP/测试，app.py 改用 asyncio.create_task。
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
    """Agent 循环的 Celery 任务包装器。"""
    logger.info("Celery 任务已启动，task_id=%s", task_id)

    from orchestration_service.app import _run_agent

    try:
        asyncio.get_event_loop().run_until_complete(_run_agent(task_id))
    except Exception:
        logger.exception("Celery 任务失败，task_id=%s", task_id)
        raise

    return {"task_id": task_id, "status": "completed"}


@task_prerun.connect
def on_task_prerun(task_id: str | None = None, task: object | None = None, **kwargs: object) -> None:
    logger.info("Celery 任务启动中: %s", task_id)


@task_failure.connect
def on_task_failure(task_id: str | None = None, exception: Exception | None = None, **kwargs: object) -> None:
    logger.error("Celery 任务失败: %s — %s", task_id, exception)
