"""FastAPI 应用的共享 Prometheus 指标检测。

在任何 PolicyAI 服务中的用法：
    from shared.metrics import setup_metrics

    app = FastAPI(...)
    setup_metrics(app)  # 检测路由 + 暴露 /metrics
"""

from __future__ import annotations

from prometheus_fastapi_instrumentator import Instrumentator
from starlette.applications import Starlette


def setup_metrics(app: Starlette, **instrumentator_kwargs: object) -> Instrumentator:
    """检测 FastAPI/Starlette 应用并暴露 `/metrics` 端点。

    返回 Instrumentator 实例，以便调用方可以在需要时添加自定义指标。
    """
    instrumentator = Instrumentator(**instrumentator_kwargs)
    instrumentator.instrument(app).expose(app)
    return instrumentator
