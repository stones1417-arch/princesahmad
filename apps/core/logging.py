from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any


_SENSITIVE_KEY_VALUE_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|cookie)"
    r"([\s:=]+)([^\s,;\"']+)",
)
_BEARER_TOKEN_PATTERN = re.compile(r"(?i)(bearer\s+)[^\s,;\"']+")

_SENSITIVE_FIELD_NAMES = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "authorization",
    "cookie",
    "set_cookie",
}


def redact_sensitive(value: Any) -> Any:
    """Remove credentials from log values before they reach any handler."""
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if str(key).lower() in _SENSITIVE_FIELD_NAMES
                else redact_sensitive(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    if isinstance(value, (list, set)):
        return [redact_sensitive(item) for item in value]
    if not isinstance(value, str):
        return value

    redacted = _BEARER_TOKEN_PATTERN.sub(r"\1[REDACTED]", value)
    return _SENSITIVE_KEY_VALUE_PATTERN.sub(
        r"\1\2[REDACTED]",
        redacted,
    )


class SensitiveDataFilter(logging.Filter):
    """Sanitize messages, arguments, and supported structured log fields."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive(record.msg)
        record.args = redact_sensitive(record.args)
        for field_name in _SENSITIVE_FIELD_NAMES:
            if hasattr(record, field_name):
                setattr(record, field_name, "[REDACTED]")
        return True


class JsonFormatter(logging.Formatter):
    """Emit small machine-readable records with scrubbed exception details."""

    structured_fields = (
        "event",
        "export_log_id",
        "report_key",
        "task_name",
        "status_code",
        "user_id",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive(record.getMessage()),
        }
        for field_name in self.structured_fields:
            value = getattr(record, field_name, None)
            if value is not None:
                payload[field_name] = redact_sensitive(value)

        if record.exc_info:
            payload["exception"] = redact_sensitive(
                self.formatException(record.exc_info)
            )

        return json.dumps(payload, ensure_ascii=False, default=str)