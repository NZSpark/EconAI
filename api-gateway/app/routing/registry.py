"""路由注册表 — 将 URL 路径模式映射到后端服务。"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class RouteRule:
    """将路径模式映射到后端服务的单条路由规则。

    模式按顺序匹配。首次匹配即获胜。
    """

    pattern: re.Pattern[str]
    service_url: str
    description: str = ""

    @classmethod
    def from_prefix(cls, prefix: str, service_url: str, description: str = "") -> RouteRule:
        """从路径前缀和服务 URL 创建路由规则。"""
        # 将前缀转换为正则: ^/prefix(?:/.*)?$
        escaped = re.escape(prefix)
        regex = f"^{escaped}(?:/.*)?$"
        return cls(pattern=re.compile(regex), service_url=service_url, description=description)


def _build_route_table(service_urls: dict[str, str]) -> list[RouteRule]:
    """从服务 URL 字典构建路由表。

    顺序很重要！更具体的路径必须放在较不具体的路径之前。
    """
    return [
        # 认证端点 -> user-service
        RouteRule.from_prefix(
            "/api/auth",
            service_urls["user_service_url"],
            description="/api/auth/* -> user-service",
        ),
        # 项目文档 -> document-service（必须放在通用项目路由之前）
        RouteRule.from_prefix(
            "/api/projects/",
            service_urls["document_service_url"],
            description="/api/projects/{id}/documents/* -> document-service（运行时检查）",
        ),
        # 项目搜索 -> kb-service（必须放在通用项目路由之前）
        RouteRule.from_prefix(
            "/api/projects/",
            service_urls["kb_service_url"],
            description="/api/projects/{id}/search -> kb-service（运行时检查）",
        ),
        # 机构搜索 -> kb-service
        RouteRule.from_prefix(
            "/api/institutional/search",
            service_urls["kb_service_url"],
            description="/api/institutional/search -> kb-service",
        ),
        # 任务详情/状态 -> orchestration-service
        RouteRule.from_prefix(
            "/api/tasks/",
            service_urls["orchestration_service_url"],
            description="/api/tasks/{id}/* -> orchestration-service",
        ),
        # 项目任务 -> orchestration-service
        RouteRule.from_prefix(
            "/api/projects/",
            service_urls["orchestration_service_url"],
            description="/api/projects/{id}/tasks/* -> orchestration-service（运行时检查）",
        ),
        # 项目 CRUD -> user-service
        RouteRule.from_prefix(
            "/api/projects",
            service_urls["user_service_url"],
            description="/api/projects/* -> user-service",
        ),
        # 管理 -> user-service
        RouteRule.from_prefix(
            "/api/admin",
            service_urls["user_service_url"],
            description="/api/admin/* -> user-service",
        ),
    ]


@dataclass
class RouteResult:
    """路由解析结果。"""

    service_url: str
    target_path: str
    description: str = ""


class RouteRegistry:
    """将传入请求路径解析到后端服务 URL 的注册表。
    
    路由解析策略：
    1. 先匹配具体的子路径（如 /api/projects/{id}/documents/...）
    2. 再匹配通用前缀（如 /api/auth/*）
    3. 优先匹配更具体的规则，避免路径冲突
    
    微服务路由映射总览：
    - /api/auth/*              → user-service         （认证）
    - /api/projects/{id}/documents/* → document-service （文档管理）
    - /api/projects/{id}/search      → kb-service      （知识库搜索）
    - /api/projects/{id}/tasks/*     → orchestration-service（任务编排）
    - /api/projects/*          → user-service         （项目 CRUD）
    - /api/tasks/{id}/export   → output-service       （文件导出）
    - /api/tasks/{id}/*        → orchestration-service（任务详情）
    - /api/institutional/search → kb-service           （机构搜索）
    - /api/admin/*             → user-service         （管理后台）
    """

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
        """将传入请求路径解析到后端服务。
        
        匹配优先级（从高到低）：
        1. /api/projects/{id}/documents/... → document-service
        2. /api/projects/{id}/search         → kb-service
        3. /api/projects/{id}/tasks/...      → orchestration-service
        4. /api/institutional/search         → kb-service
        5. /api/tasks/{id}/export            → output-service
        6. /api/tasks/{id}/...               → orchestration-service
        7. /api/auth/*                       → user-service
        8. /api/projects/*                   → user-service
        9. /api/admin/*                      → user-service
        """
        # ——— 项目路由的特定子路径检查（具体路径优先）———

        # /api/projects/{id}/documents/... → 文档上传/管理
        match = re.match(r"^/api/projects/([^/]+)/documents(?:/.*)?$", path)
        if match:
            from app.config import settings

            return RouteResult(
                service_url=settings.document_service_url,
                target_path=path,
                description="-> document-service",
            )

        # /api/projects/{id}/search → 项目内知识库搜索
        match = re.match(r"^/api/projects/([^/]+)/search$", path)
        if match:
            from app.config import settings

            return RouteResult(
                service_url=settings.kb_service_url,
                target_path=path,
                description="-> kb-service",
            )

        # /api/projects/{id}/tasks/... → 在项目下创建/管理任务
        match = re.match(r"^/api/projects/([^/]+)/tasks(?:/.*)?$", path)
        if match:
            from app.config import settings

            return RouteResult(
                service_url=settings.orchestration_service_url,
                target_path=path,
                description="-> orchestration-service",
            )

        # /api/institutional/search → 跨机构知识库搜索
        if path.startswith("/api/institutional/search"):
            from app.config import settings

            return RouteResult(
                service_url=settings.kb_service_url,
                target_path=path,
                description="-> kb-service",
            )

        # /api/tasks/{id}/export → 任务结果文件导出（Word/PDF）
        if re.match(r"^/api/tasks/([^/]+)/export$", path):
            from app.config import settings

            return RouteResult(
                service_url=settings.output_service_url,
                target_path=path,
                description="-> output-service（文件下载）",
            )

        # /api/tasks/{id}/... → 任务详情/状态查询（非项目子路由）
        if re.match(r"^/api/tasks/([^/]+)(?:/.*)?$", path):
            from app.config import settings

            return RouteResult(
                service_url=settings.orchestration_service_url,
                target_path=path,
                description="-> orchestration-service",
            )

        # ——— 基于通用前缀的规则（兜底匹配）———

        # /api/auth/* → 登录、刷新令牌等
        if path.startswith("/api/auth"):
            from app.config import settings

            return RouteResult(
                service_url=settings.user_service_url,
                target_path=path,
                description="-> user-service",
            )

        # /api/projects/* → 项目 CRUD（非文档/搜索/任务的剩余路径）
        if path.startswith("/api/projects"):
            from app.config import settings

            return RouteResult(
                service_url=settings.user_service_url,
                target_path=path,
                description="-> user-service",
            )

        # /api/admin/* → 用户管理、组织管理、审计日志
        if path.startswith("/api/admin"):
            from app.config import settings

            return RouteResult(
                service_url=settings.user_service_url,
                target_path=path,
                description="-> user-service",
            )

        return None


# 单例
_route_registry: RouteRegistry | None = None


def get_route_registry(service_urls: dict[str, str] | None = None) -> RouteRegistry:
    """获取或创建单例 RouteRegistry。"""
    global _route_registry
    if _route_registry is None:
        _route_registry = RouteRegistry(service_urls)
    return _route_registry
