"""适配器异常层次结构，用于标准化的错误处理。"""

from __future__ import annotations


class AdapterError(Exception):
    """适配器基础错误。"""


class AdapterRateLimitError(AdapterError):
    """频率限制（429）错误 — 可通过指数退避重试。"""


class AdapterServerError(AdapterError):
    """5xx 服务器错误 — 可通过线性退避重试。"""


class AdapterTimeoutError(AdapterError):
    """请求超时 — 可重试一次，然后返回 504。"""


class AdapterConnectionError(AdapterError):
    """连接失败 — 可能触发熔断器。"""


class AdapterAuthError(AdapterError):
    """认证/授权错误 — 不可重试。"""


class AdapterModelUnavailableError(AdapterError):
    """模型不可用（例如 OOM）— 503。"""
