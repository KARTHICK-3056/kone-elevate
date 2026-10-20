"""Logging configuration for the backend process.

Structured JSON, one object per line, with the request id threaded through
every log record via ``app.core.request_context``. Plain-text logs to
stdout were the P4 finding: "you cannot answer 'why was that prediction
slow' or 'how often do we abstain'" without a way to correlate every log
line touched by one request, or feed logs into anything that parses them.
JSON-per-line is what a log shipper (CloudWatch, Loki, Datadog, `jq` on a
laptop) expects; the previous ``%(asctime)s | %(levelname)-8s | ...``
formatter was readable by a human tailing a terminal and nothing else.
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from logging.config import dictConfig
from typing import Any, Dict

from app.core.config import settings
from app.core.request_context import get_request_id

#: Attributes every stdlib LogRecord carries - anything else on the record
#: (passed via `logger.info(..., extra={...})`) is application-supplied and
#: gets folded into the JSON object too.
_STANDARD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())


class JSONFormatter(logging.Formatter):
    """Renders one LogRecord as one JSON object, newline-terminated."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id

        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRS or key in payload:
                continue
            try:
                json.dumps(value)
            except TypeError:
                value = repr(value)
            payload[key] = value

        if record.exc_info:
            payload["exception"] = "".join(traceback.format_exception(*record.exc_info))

        return json.dumps(payload, default=str)


class HumanFormatter(logging.Formatter):
    """The original single-line format, for a developer tailing a terminal."""

    def format(self, record: logging.LogRecord) -> str:
        request_id = get_request_id()
        prefix = f"[{request_id[:8]}] " if request_id else ""
        base = super().format(record)
        return f"{prefix}{base}"


def configure_logging() -> None:
    """Apply a consistent logging configuration to the whole process.

    ``LOG_FORMAT=json`` (the default) is what a real deployment wants;
    ``LOG_FORMAT=human`` keeps the original readable one-liner for a
    developer running the API directly in a terminal.
    """
    use_json = settings.LOG_FORMAT.lower() != "human"
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {"()": JSONFormatter},
                "human": {
                    "()": HumanFormatter,
                    "format": "%(asctime)s | %(levelname)-8s | %(name)-28s | %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "json" if use_json else "human",
                    "stream": sys.stdout,
                },
            },
            "root": {"handlers": ["console"], "level": settings.LOG_LEVEL},
            "loggers": {
                "uvicorn": {"level": settings.LOG_LEVEL, "propagate": True, "handlers": []},
                "uvicorn.error": {"level": settings.LOG_LEVEL, "propagate": True, "handlers": []},
                "uvicorn.access": {"level": "WARNING", "propagate": True, "handlers": []},
                "sqlalchemy.engine": {"level": "WARNING"},
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger."""
    return logging.getLogger(name)
