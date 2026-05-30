"""所有 PolicyAI 服务的结构化 JSON 日志配置。"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime


class JSONFormatter(logging.Formatter):
    """以 JSON 行格式输出日志记录，用于结构化日志。"""

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


def setup_logging(level: str = "INFO", service_name: str = "policyai") -> None:
    """将根日志记录器配置为 JSON 输出到标准输出。"""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    # 移除现有的处理器以避免重复
    root.handlers.clear()
    root.addHandler(handler)

    logging.getLogger(service_name).info("Logging configured", extra={"level": level})
