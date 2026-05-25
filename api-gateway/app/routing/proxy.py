"""HTTP proxy to backend services using httpx."""

from __future__ import annotations

import asyncio

import httpx
from fastapi import Request
from starlette.responses import Response, StreamingResponse

from app.config import settings


class ProxyError(Exception):
    """Raised when proxy to backend fails."""


class ServiceProxy:
    """Async HTTP proxy that forwards requests to backend microservices.

    Streams responses for large payloads. Includes retry with exponential backoff.
    """

    def __init__(self, client: httpx.AsyncClient | None = None):
        if client is None:
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.proxy_timeout_s),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        self._client = client
        self._max_retries = settings.proxy_max_retries

    async def forward(self, service_url: str, path: str, request: Request) -> Response:
        """Forward an incoming request to a backend service.

        Args:
            service_url: Base URL of the backend service (e.g., http://user-service:8007).
            path: The full request path (e.g., /api/auth/login).
            request: The original FastAPI request.

        Returns:
            A Starlette Response from the backend.

        Raises:
            ProxyError: If forwarding fails after retries.
        """
        target_url = f"{service_url.rstrip('/')}{path}"

        # Forward query parameters
        if request.url.query:
            target_url = f"{target_url}?{request.url.query}"

        # Prepare headers — forward most but strip hop-by-hop
        headers = dict(request.headers)
        headers.pop("host", None)
        headers.pop("transfer-encoding", None)
        headers.pop("content-length", None)

        # Add forwarded user info
        if hasattr(request.state, "user"):
            user = request.state.user
            headers["X-User-ID"] = user.get("user_id", "")
            headers["X-Username"] = user.get("username", "")
            headers["X-User-Role"] = user.get("role", "")
            headers["X-User-Group-IDs"] = ",".join(user.get("group_ids", []))

        if hasattr(request.state, "request_id"):
            headers["X-Request-ID"] = request.state.request_id

        # Read request body
        body = await request.body()

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=body,
                    follow_redirects=False,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                if attempt < self._max_retries:
                    await asyncio.sleep(2**attempt * 0.5)
                continue

            # Build streaming response if content is large, otherwise regular
            content_type = response.headers.get("content-type", "")
            content_length = response.headers.get("content-length")

            response_headers = dict(response.headers)
            response_headers.pop("transfer-encoding", None)
            response_headers.pop("content-encoding", None)

            # Strip hop-by-hop headers
            for h in ("connection", "keep-alive", "proxy-authenticate",
                       "proxy-authorization", "te", "trailers"):
                response_headers.pop(h, None)

            if content_length and int(content_length) > 1024 * 1024:
                # Stream large responses
                return StreamingResponse(
                    response.aiter_bytes(),
                    status_code=response.status_code,
                    headers=response_headers,
                    media_type=content_type or None,
                )
            else:
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=response_headers,
                    media_type=content_type or None,
                )

        raise ProxyError(
            f"Failed to proxy to {target_url} after {self._max_retries + 1} attempts: {last_error}"
        )

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()


# Global singleton proxy
_proxy: ServiceProxy | None = None


def get_proxy() -> ServiceProxy:
    """Get or create the singleton ServiceProxy."""
    global _proxy
    if _proxy is None:
        _proxy = ServiceProxy()
    return _proxy
