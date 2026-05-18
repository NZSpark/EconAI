"""Celery configuration values, read from environment variables."""

from __future__ import annotations

import os

CELERY_BROKER_URL: str = os.getenv(
    "CELERY_BROKER_URL", "redis://:econai_redis_change_me@redis:6379/0"
)
CELERY_RESULT_BACKEND: str = os.getenv(
    "CELERY_RESULT_BACKEND", "redis://:econai_redis_change_me@redis:6379/1"
)

CELERY_WORKER_CONCURRENCY: int = int(os.getenv("CELERY_WORKER_CONCURRENCY", "4"))
CELERY_WORKER_MAX_MEMORY_PER_CHILD: int = int(
    os.getenv("CELERY_WORKER_MAX_MEMORY_PER_CHILD", "512000")
)
CELERY_TASK_TIME_LIMIT: int = int(os.getenv("CELERY_TASK_TIME_LIMIT", "1800"))
CELERY_TASK_SOFT_TIME_LIMIT: int = int(
    os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "1500")
)

CELERY_TASK_ROUTES: dict[str, dict[str, str]] = {
    "econai.document.*": {"queue": "document"},
    "econai.orchestration.*": {"queue": "orchestration"},
}