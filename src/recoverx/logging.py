"""Structured logging for RecoverX.

Follows forensic and safety rules:
- No file contents or sensitive user filenames are logged by default.
- Outputs structured log entries with timestamp, level, component, and metadata.
"""

import datetime
import json
import logging
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.datetime.fromtimestamp(
                record.created, tz=datetime.UTC
            ).isoformat(),
            "level": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
        }

        # Include structured extra fields if attached to record
        structured_data = getattr(record, "structured_data", None)
        if isinstance(structured_data, Mapping):
            log_entry["data"] = dict(structured_data)

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


class StructuredLoggerAdapter(logging.LoggerAdapter[logging.Logger]):
    """Logger adapter that attaches structured contextual metadata."""

    def __init__(self, logger: logging.Logger, extra: Mapping[str, Any] | None = None) -> None:
        super().__init__(logger, dict(extra) if extra is not None else {})

    def process(
        self, msg: Any, kwargs: MutableMapping[str, Any]
    ) -> tuple[Any, MutableMapping[str, Any]]:
        extra = dict(self.extra) if self.extra else {}
        if "extra" in kwargs and isinstance(kwargs["extra"], Mapping):
            extra.update(kwargs.pop("extra"))
        kwargs["extra"] = {"structured_data": extra}
        return msg, kwargs


def setup_logging(
    level: int = logging.INFO,
    json_format: bool = True,
    stream: Any = None,
) -> logging.Logger:
    """Configure root logging for RecoverX."""
    root_logger = logging.getLogger("recoverx")
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setLevel(level)

    if json_format:
        handler.setFormatter(StructuredJsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(handler)
    return root_logger


def get_logger(name: str, **context: Any) -> StructuredLoggerAdapter:
    """Obtain a structured logger for a component with contextual fields."""
    logger = logging.getLogger(f"recoverx.{name}")
    return StructuredLoggerAdapter(logger, extra=context)
