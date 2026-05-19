"""Unified error response formatting and exception handlers."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.routing.proxy import ProxyError


class AppError(Exception):
    """Base application error with error code."""

    def __init__(self, code: str, message: str, status_code: int = 500, details: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


def to_error_response(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the standard error response format.

    Returns:
        {"error": {"code": "...", "message": "...", "details": {}}}
    """
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    """Register all error handlers on the FastAPI app."""

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=to_error_response(
                "RESOURCE_NOT_FOUND",
                "The requested resource was not found.",
            ),
        )

    @app.exception_handler(405)
    async def method_not_allowed_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=405,
            content=to_error_response(
                "METHOD_NOT_ALLOWED",
                f"Method {request.method} not allowed for {request.url.path}.",
            ),
        )

    @app.exception_handler(ProxyError)
    async def proxy_error_handler(request: Request, exc: ProxyError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=to_error_response(
                "SERVICE_UNAVAILABLE",
                str(exc),
            ),
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=to_error_response(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=to_error_response(
                "SYS_INTERNAL_ERROR",
                "An internal server error occurred.",
            ),
        )
