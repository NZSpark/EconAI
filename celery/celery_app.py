"""PolicyAI 的 Celery 应用工厂。"""

from __future__ import annotations

from celery import Celery

from celery_config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND, CELERY_TASK_ROUTES

celery_app = Celery(
    "policyai",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[],  # 任务由各服务在导入时注册
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=200,
    task_routes=CELERY_TASK_ROUTES,
    task_annotations={
        "policyai.document.*": {"queue": "document"},
        "policyai.orchestration.*": {"queue": "orchestration"},
    },
    beat_schedule={},
)
