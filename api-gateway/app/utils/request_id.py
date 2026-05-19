"""X-Request-ID handling — inject and propagate request IDs."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject X-Request-ID header if not present; propagate to response."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", "")
        if not request_id:
            request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        request.headers.__dict__.setdefault("x-request-id", request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
