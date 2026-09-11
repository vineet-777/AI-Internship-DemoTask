"""Small JSON logging adapter shared by pipeline components."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

LOGGER_NAME = "ai_intelligence_pipeline"


class JsonFormatter(logging.Formatter):
    """Render a stable JSON event that is useful locally and in log platforms."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        fields = getattr(record, "event_fields", {})
        payload.update(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, sort_keys=True)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    return logger


def log_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    configure_logging().log(level, event, extra={"event_fields": fields})
