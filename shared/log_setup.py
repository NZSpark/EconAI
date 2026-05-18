"""Structured JSON logging setup for all EconAI services."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime


class JSONFormatter(logging.Formatter):
    """Emit log records as JSON lines for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        log_entry: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: str = "INFO", service_name: str = "econai") -> None:
    """Configure root logger with JSON output to stdout."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    # Remove existing handlers to avoid duplicates
    root.handlers.clear()
    root.addHandler(handler)

    logging.getLogger(service_name).info("Logging configured", extra={"level": level})
