"""Adapter exception hierarchy for standardized error handling."""

from __future__ import annotations


class AdapterError(Exception):
    """Base adapter error."""


class AdapterRateLimitError(AdapterError):
    """Rate limit (429) error — retryable with exponential backoff."""


class AdapterServerError(AdapterError):
    """5xx server error — retryable with linear backoff."""


class AdapterTimeoutError(AdapterError):
    """Request timeout — retryable once, then 504."""


class AdapterConnectionError(AdapterError):
    """Connection failure — may trigger circuit breaker."""


class AdapterAuthError(AdapterError):
    """Authentication / authorization error — not retryable."""


class AdapterModelUnavailableError(AdapterError):
    """Model unavailable (e.g., OOM) — 503."""
