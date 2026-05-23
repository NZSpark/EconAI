"""Shared Prometheus metrics instrumentation for FastAPI apps.

Usage in any EconAI service:
    from shared.metrics import setup_metrics

    app = FastAPI(...)
    setup_metrics(app)  # instrument routes + expose /metrics
"""

from __future__ import annotations

from prometheus_fastapi_instrumentator import Instrumentator
from starlette.applications import Starlette


def setup_metrics(app: Starlette, **instrumentator_kwargs: object) -> Instrumentator:
    """Instrument a FastAPI/Starlette app and expose `/metrics` endpoint.

    Returns the Instrumentator instance so callers can add custom metrics if needed.
    """
    instrumentator = Instrumentator(**instrumentator_kwargs)
    instrumentator.instrument(app).expose(app)
    return instrumentator
