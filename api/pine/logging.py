import contextvars
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

_ACCOUNT_RE = re.compile(r"\b\d{8,}\b")


def redact(text: str) -> str:
    """Mask runs of 8+ digits (bank account numbers) in log output."""
    return _ACCOUNT_RE.sub(lambda m: m.group(0)[:2] + "*" * (len(m.group(0)) - 2), text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        request_id = getattr(record, "request_id", None) or request_id_ctx.get()
        if request_id:
            entry["request_id"] = request_id
        for key in ("deal_id", "run_id", "agent", "job_id", "tool", "latency_ms"):
            value = getattr(record, key, None)
            if value is not None:
                entry[key] = value
        if record.exc_info:
            entry["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
