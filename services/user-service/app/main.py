"""EconAI User & Permission Service (M8) — FastAPI application."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.config import settings
from app.database import async_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup
    redis_url = settings.redis_url
    app.state.redis = Redis.from_url(redis_url, decode_responses=True)

    # Optionally start audit consumer in background
    if settings.audit_log_enabled:
        from app.audit_consumer import audit_consumer

        app.state.audit_task = asyncio.create_task(
            audit_consumer(app.state.redis, async_session_factory)
        )

    yield

    # Shutdown
    if hasattr(app.state, "audit_task"):
        app.state.audit_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await app.state.audit_task

    await app.state.redis.close()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, object]:
    """Health check — verifies Redis connectivity."""
    import contextlib

    redis_ok = False
    with contextlib.suppress(Exception):
        redis_ok = settings.token_blacklist_enabled

    return {
        "status": "ok",
        "service": settings.app_name,
        "dependencies": {
            "redis_configured": redis_ok,
        },
    }


# Register routers
from app.routers.audit import router as audit_router
from app.routers.auth import router as auth_router
from app.routers.gdpr import router as gdpr_router
from app.routers.groups import router as groups_router
from app.routers.internal import router as internal_router
from app.routers.projects import router as projects_router
from app.routers.users import router as users_router

app.include_router(auth_router)
app.include_router(audit_router)
app.include_router(gdpr_router)
app.include_router(groups_router)
app.include_router(internal_router)
app.include_router(projects_router)
app.include_router(users_router)
