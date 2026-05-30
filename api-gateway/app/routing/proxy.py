"""使用 httpx 的后端服务 HTTP 代理。"""

from __future__ import annotations

import asyncio

import httpx
from fastapi import Request
from starlette.responses import Response, StreamingResponse

from app.config import settings


class ProxyError(Exception):
    """当代理到后端失败时抛出。"""


class ServiceProxy:
    """异步 HTTP 代理，将请求转发到后端微服务。
    
    核心功能：
    - 请求转发：将 FastAPI 的 Request 原样转发到后端服务的 HTTP 接口
    - 用户信息注入：通过 X-User-ID / X-Username / X-User-Role 头传递认证信息
    - 指数退避重试：网络错误时按 0.5s, 1s, 2s... 递增等待后重试
    - 大响应流式传输：超过 1MB 的响应使用 StreamingResponse 避免内存爆炸
    - 逐跳头部清理：移除 host, transfer-encoding 等不该转发给后端的 HTTP 头
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
        """将传入请求转发到后端服务。

        参数:
            service_url: 后端服务的基础 URL（例如 http://user-service:8007）。
            path: 完整的请求路径（例如 /api/auth/login）。
            request: 原始的 FastAPI 请求。

        返回:
            来自后端的 Starlette Response。

        抛出:
            ProxyError: 如果重试后转发仍然失败。
        """
        # 拼接目标 URL（保留原始 path + query string）
        target_url = f"{service_url.rstrip('/')}{path}"
        if request.url.query:
            target_url = f"{target_url}?{request.url.query}"

        # 准备请求头：复制客户端头，移除逐跳头
        headers = dict(request.headers)
        headers.pop("host", None)              # 后端服务用自己的 host
        headers.pop("transfer-encoding", None) # 分块编码由 httpx 管理
        headers.pop("content-length", None)    # httpx 会自动计算

        # 注入认证后的用户信息到自定义请求头，后端服务可读取
        if hasattr(request.state, "user"):
            user = request.state.user
            headers["X-User-ID"] = user.get("user_id", "")
            headers["X-Username"] = user.get("username", "")
            headers["X-User-Role"] = user.get("role", "")
            # 注意: X-User-Group-IDs 有意省略
            # 如果用户属于大量组织，HTTP 头会超过 4KB 限制导致 431 错误
            # 后端服务直接从数据库查询用户的组织成员关系

        if hasattr(request.state, "request_id"):
            headers["X-Request-ID"] = request.state.request_id

        # 读取完整的请求体（FastAPI Request body 是流，只能读一次）
        body = await request.body()

        # 指数退避重试循环
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=body,
                    follow_redirects=False,  # 不自动跟随重定向，透传给客户端
                )
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                if attempt < self._max_retries:
                    # 指数退避: 0.5s, 1s, 2s, 4s...
                    await asyncio.sleep(2**attempt * 0.5)
                continue

            # 构建响应：大文件流式返回，小文件直接返回
            content_type = response.headers.get("content-type", "")
            content_length = response.headers.get("content-length")

            response_headers = dict(response.headers)
            response_headers.pop("transfer-encoding", None)
            response_headers.pop("content-encoding", None)

            # 清理逐跳响应头（这些头只对代理→后端有意义，不应返回给客户端）
            for h in ("connection", "keep-alive", "proxy-authenticate",
                       "proxy-authorization", "te", "trailers"):
                response_headers.pop(h, None)

            if content_length and int(content_length) > 1024 * 1024:
                # 大响应（>1MB）：使用 StreamingResponse 流式传输
                # 避免一次性加载整个响应体到内存
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
            f"代理到 {target_url} 失败，已尝试 {self._max_retries + 1} 次: {last_error}"
        )

    async def close(self) -> None:
        """关闭底层的 httpx 客户端，释放连接池。"""
        await self._client.aclose()


# 全局单例代理
_proxy: ServiceProxy | None = None


def get_proxy() -> ServiceProxy:
    """获取或创建单例 ServiceProxy。"""
    global _proxy
    if _proxy is None:
        _proxy = ServiceProxy()
    return _proxy
