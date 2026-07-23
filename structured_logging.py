"""Structured JSON logging for PRISM.

Provides a JSON formatter for machine-readable logs and a plain-text formatter
for development.  Configure via the ``LOG_FORMAT`` environment variable
(``json`` or ``text``, default ``text``).

Usage::

    from structured_logging import setup_logging
    setup_logging()
"""

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra_data"):
            log_entry["extra"] = record.extra_data
        return json.dumps(log_entry, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable formatter for development."""

    FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    def __init__(self) -> None:
        super().__init__(fmt=self.FORMAT, datefmt=self.DATE_FORMAT)


def setup_logging(level: int = logging.INFO, log_format: str = "text") -> None:
    """Configure root logger and PRISM loggers.

    Args:
        level: Minimum log level.
        log_format: ``"json"`` for machine-readable, ``"text"`` for human.
    """
    root = logging.getLogger()
    root.setLevel(level)

    for handler in root.handlers[:]:
        root.removeHandler(handler)

    stream = logging.StreamHandler(sys.stdout)
    stream.setLevel(level)

    if log_format == "json":
        stream.setFormatter(JSONFormatter())
    else:
        stream.setFormatter(TextFormatter())

    root.addHandler(stream)

    for noisy in ("urllib3", "werkzeug", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
