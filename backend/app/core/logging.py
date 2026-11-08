"""Structured logs: one JSON object per line on stdout (A-66, D-32).

Personal data never reaches a log line. The access log records the route template
(`/api/bookings/{reference}`), never the real path or the query string, and no request
or response bodies. Errors are logged as the exception type and the code locations of
the traceback, without the exception message, because messages can carry values (a
database error can quote an email address).
"""

import json
import logging
import re
import sys
import traceback
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Extra fields a log call may attach. Anything else passed as `extra` is ignored, so a
# careless log call cannot leak a field nobody reviewed.
_ALLOWED_FIELDS = (
    "method",
    "route",
    "status",
    "duration_ms",
    "error_type",
    "error_at",
    "limit",
    "reference",  # a booking or enquiry reference; not personal data
)

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def safe_request_id(value: str | None) -> str | None:
    """Accept a caller's X-Request-ID only if it cannot inject anything into logs."""
    return value if value and _SAFE_REQUEST_ID.fullmatch(value) else None


def _short_path(filename: str) -> str:
    return "/".join(filename.replace("\\", "/").split("/")[-2:])


def exception_fields(exc: BaseException) -> dict[str, object]:
    frames = traceback.extract_tb(exc.__traceback__)
    locations = [f"{_short_path(f.filename)}:{f.lineno} in {f.name}" for f in frames]
    return {"error_type": type(exc).__name__, "error_at": locations[-8:]}


_base_factory = logging.getLogRecordFactory()


def _record_with_request_id(*args: object, **kwargs: object) -> logging.LogRecord:
    """Stamp the current request id on every record when it is created, so it survives
    even if a handler formats the record later, outside the request's context."""
    record = _base_factory(*args, **kwargs)
    if not hasattr(record, "request_id"):
        record.request_id = request_id_var.get()
    return record


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id:
            entry["request_id"] = request_id
        for field in _ALLOWED_FIELDS:
            if hasattr(record, field):
                entry[field] = getattr(record, field)
        if record.exc_info and record.exc_info[1] is not None:
            entry.update(exception_fields(record.exc_info[1]))
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    logging.setLogRecordFactory(_record_with_request_id)
    # HTTP client libraries log full URLs at INFO, query strings included; keep them quiet.
    for name in ("httpx", "httpx2", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    # Uvicorn's own access log prints the raw path and query string; ours replaces it.
    access = logging.getLogger("uvicorn.access")
    access.handlers, access.propagate, access.disabled = [], False, True
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
