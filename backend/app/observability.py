import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Generator
from uuid import UUID

_log_context: ContextVar[dict[str, Any]] = ContextVar("log_context", default={})


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        ctx = _log_context.get()
        if ctx:
            payload.update(ctx)
        if hasattr(record, "extra_fields"):
            payload.update(record.extra_fields)  # type: ignore[attr-defined]
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


@contextmanager
def log_context(**fields: Any) -> Generator[None, None, None]:
    current = _log_context.get().copy()
    current.update({k: str(v) if isinstance(v, UUID) else v for k, v in fields.items() if v is not None})
    token = _log_context.set(current)
    try:
        yield
    finally:
        _log_context.reset(token)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


@contextmanager
def trace_span(name: str, **attributes: Any) -> Generator[None, None, None]:
    """No-op span wrapper. OpenTelemetry can replace this later."""
    with log_context(span=name, **attributes):
        yield
