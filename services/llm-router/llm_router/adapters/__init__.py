"""LLM adapters: ClaudeAdapter, LocalAdapter, and exception types."""

from llm_router.adapters.claude_adapter import ClaudeAdapter
from llm_router.adapters.exceptions import (
    AdapterAuthError,
    AdapterConnectionError,
    AdapterError,
    AdapterModelUnavailableError,
    AdapterRateLimitError,
    AdapterServerError,
    AdapterTimeoutError,
)
from llm_router.adapters.local_adapter import LocalAdapter

__all__ = [
    "AdapterAuthError",
    "AdapterConnectionError",
    "AdapterError",
    "AdapterModelUnavailableError",
    "AdapterRateLimitError",
    "AdapterServerError",
    "AdapterTimeoutError",
    "ClaudeAdapter",
    "LocalAdapter",
]
