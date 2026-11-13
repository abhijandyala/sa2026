"""Request logging that never records grower-entered data.

Logged per request: method, path (no query string), status, duration. Request and response
bodies are never logged. As a second line of defence a filter redacts any grower field that
ends up in a log message by accident (``residue_report``, ``observations``,
``low_moisture_concern``, ``grower``).
"""

from __future__ import annotations

import logging
import re
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

LOGGER_NAME = "fieldshift.access"
_GROWER_KEYS = ("residue_report", "observations", "low_moisture_concern", "grower")
_KEYS = "|".join(_GROWER_KEYS)
_VALUE = r"""(\{[^}]*\}|\[[^\]]*\]|"[^"]*"|'[^']*'|[^,}\s]+)"""
_REDACT = re.compile(r"""(["']?(?:""" + _KEYS + r""")["']?\s*[:=]\s*)""" + _VALUE)


class ScrubFilter(logging.Filter):
    """Redacts grower fields that appear in a log record's message."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - never break logging
            return True
        scrubbed = _REDACT.sub(r"\1[redacted]", msg)
        if scrubbed != msg:
            record.msg, record.args = scrubbed, None
        return True


def install_scrub_filter() -> None:
    """Attach the filter to the root logger's handlers and to our own logger."""
    logging.getLogger(LOGGER_NAME).addFilter(ScrubFilter())
    logging.getLogger("fieldshift").addFilter(ScrubFilter())
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, ScrubFilter) for f in handler.filters):
            handler.addFilter(ScrubFilter())


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        started = time.perf_counter()
        response = await call_next(request)
        logging.getLogger(LOGGER_NAME).info(
            "%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code,
            (time.perf_counter() - started) * 1000,
        )
        return response
