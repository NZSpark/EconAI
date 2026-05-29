"""Route registry — maps URL path patterns to backend services."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class RouteRule:
    """A single routing rule mapping a path pattern to a backend service.

    Patterns are matched in order. First match wins.
    """

    pattern: re.Pattern[str]
    service_url: str
    description: str = ""

    @classmethod
    def from_prefix(cls, prefix: str, service_url: str, description: str = "") -> RouteRule:
        """Create a route rule from a path prefix and service URL."""
        # Convert prefix to regex: ^/prefix(?:/.*)?$
        escaped = re.escape(prefix)
        regex = f"^{escaped}(?:/.*)?$"
        return cls(pattern=re.compile(regex), service_url=service_url, description=description)


def _build_route_table(service_urls: dict[str, str]) -> list[RouteRule]:
    """Build the route table from service URLs dict.

    Order matters! More specific paths must come before less specific ones.
    """
    return [
        # Auth endpoints -> user-service
        RouteRule.from_prefix(
            "/api/auth",
            service_urls["user_service_url"],
            description="/api/auth/* -> user-service",
        ),
        # Project documents -> document-service (must come before generic project routes)
        RouteRule.from_prefix(
            "/api/projects/",
            service_urls["document_service_url"],
            description="/api/projects/{id}/documents/* -> document-service (checked at runtime)",
        ),
        # Project search -> kb-service (must come before generic project routes)
        RouteRule.from_prefix(
            "/api/projects/",
            service_urls["kb_service_url"],
            description="/api/projects/{id}/search -> kb-service (checked at runtime)",
        ),
        # Institutional search -> kb-service
        RouteRule.from_prefix(
            "/api/institutional/search",
            service_urls["kb_service_url"],
            description="/api/institutional/search -> kb-service",
        ),
        # Task detail/status -> orchestration-service
        RouteRule.from_prefix(
            "/api/tasks/",
            service_urls["orchestration_service_url"],
            description="/api/tasks/{id}/* -> orchestration-service",
        ),
        # Project tasks -> orchestration-service
        RouteRule.from_prefix(
            "/api/projects/",
            service_urls["orchestration_service_url"],
            description="/api/projects/{id}/tasks/* -> orchestration-service (checked at runtime)",
        ),
        # Project CRUD -> user-service
        RouteRule.from_prefix(
            "/api/projects",
            service_urls["user_service_url"],
            description="/api/projects/* -> user-service",
        ),
        # Admin -> user-service
        RouteRule.from_prefix(
            "/api/admin",
            service_urls["user_service_url"],
            description="/api/admin/* -> user-service",
        ),
    ]


@dataclass
class RouteResult:
    """Result of route resolution."""

    service_url: str
    target_path: str
    description: str = ""


class RouteRegistry:
    """Registry that resolves incoming request paths to backend service URLs."""

    def __init__(self, service_urls: dict[str, str] | None = None):
        if service_urls is None:
            from app.config import settings

            service_urls = {
                "user_service_url": settings.user_service_url,
                "document_service_url": settings.document_service_url,
                "kb_service_url": settings.kb_service_url,
                "orchestration_service_url": settings.orchestration_service_url,
                "llm_router_url": settings.llm_router_url,
                "citation_service_url": settings.citation_service_url,
                "output_service_url": settings.output_service_url,
            }
        self._rules = _build_route_table(service_urls)

    def resolve(self, path: str) -> RouteResult | None:
        """Resolve an incoming request path to a backend service.

        The routing logic uses specific sub-path matching within project routes:
        - /api/projects/{id}/documents/* -> document-service
        - /api/projects/{id}/search -> kb-service
        - /api/projects/{id}/tasks/* -> orchestration-service
        - /api/projects/* -> user-service
        - /api/tasks/{id}/* -> orchestration-service
        """
        # ——— Specific sub-path checks for project routes ———

        # Document routes: /api/projects/{id}/documents/...
        match = re.match(r"^/api/projects/([^/]+)/documents(?:/.*)?$", path)
        if match:
            from app.config import settings

            return RouteResult(
                service_url=settings.document_service_url,
                target_path=path,
                description="-> document-service",
            )

        # Search routes: /api/projects/{id}/search
        match = re.match(r"^/api/projects/([^/]+)/search$", path)
        if match:
            from app.config import settings

            return RouteResult(
                service_url=settings.kb_service_url,
                target_path=path,
                description="-> kb-service",
            )

        # Task routes under project: /api/projects/{id}/tasks/...
        match = re.match(r"^/api/projects/([^/]+)/tasks(?:/.*)?$", path)
        if match:
            from app.config import settings

            return RouteResult(
                service_url=settings.orchestration_service_url,
                target_path=path,
                description="-> orchestration-service",
            )

        # Institutional search
        if path.startswith("/api/institutional/search"):
            from app.config import settings

            return RouteResult(
                service_url=settings.kb_service_url,
                target_path=path,
                description="-> kb-service",
            )

        # Task export routes: /api/tasks/{id}/export -> output-service
        if re.match(r"^/api/tasks/([^/]+)/export$", path):
            from app.config import settings

            return RouteResult(
                service_url=settings.output_service_url,
                target_path=path,
                description="-> output-service (file download)",
            )

        # Task routes (non-project): /api/tasks/{id}/...
        if re.match(r"^/api/tasks/([^/]+)(?:/.*)?$", path):
            from app.config import settings

            return RouteResult(
                service_url=settings.orchestration_service_url,
                target_path=path,
                description="-> orchestration-service",
            )

        # ——— Generic prefix-based rules ———

        # Auth -> user-service
        if path.startswith("/api/auth"):
            from app.config import settings

            return RouteResult(
                service_url=settings.user_service_url,
                target_path=path,
                description="-> user-service",
            )

        # Projects -> user-service
        if path.startswith("/api/projects"):
            from app.config import settings

            return RouteResult(
                service_url=settings.user_service_url,
                target_path=path,
                description="-> user-service",
            )

        # Admin -> user-service
        if path.startswith("/api/admin"):
            from app.config import settings

            return RouteResult(
                service_url=settings.user_service_url,
                target_path=path,
                description="-> user-service",
            )

        return None


# Singleton
_route_registry: RouteRegistry | None = None


def get_route_registry(service_urls: dict[str, str] | None = None) -> RouteRegistry:
    """Get or create the singleton RouteRegistry."""
    global _route_registry
    if _route_registry is None:
        _route_registry = RouteRegistry(service_urls)
    return _route_registry
